"""Source adapters. Every adapter returns a Result so one broken source can't sink a run.

Sources (free public access or free tiers; quotas and access policies still apply):
  hn         Hacker News / Algolia           no key
  se         Stack Exchange                  optional free STACKEXCHANGE_KEY
  reddit     Reddit                          OAuth credentials recommended; review current API terms
  bluesky    Bluesky public posts            no key; public API
  github     GitHub issues and repositories  optional GITHUB_TOKEN
  gitlab     GitLab public issue search      optional free GITLAB_TOKEN
  scholar    OpenAlex papers                 optional free OPENALEX_API_KEY
  arxiv      CS/AI and other preprints       no key; 3-second shared request spacing
  europepmc  Biomedical papers and preprints no key
  petitions  UK Parliament petitions         no key; UK only
  nyc311     NYC 311 complaints              no key; NYC only
  openFDA    Medical-device event reports    no key; US only
"""
from __future__ import annotations

import html
import os
import re
import time
from dataclasses import dataclass, field
from threading import Lock
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx

UA = "problem-radar/0.2 (open-source research tool)"
TIMEOUT = 12.0
TAGS = re.compile(r"<[^>]+>")

# Cross-call shared per-process request budgets. This is a no-wait token bucket:
# each provider can absorb a burst of two calls, then refills gradually. It prevents
# concurrent MCP visitors from turning each per-call cap into an upstream burst.
# The bucket is intentionally conservative and is not a replacement for each API's
# own quota headers or a durable limiter across multiple server instances.
_REQUEST_BUDGET_LOCK = Lock()
_REQUEST_BURST = 2.0
_REQUEST_BUCKETS: dict[str, dict[str, float]] = {}
_REQUEST_INTERVALS = {
    "github": 2.0 if os.environ.get("GITHUB_TOKEN", "").strip() else 6.0,
    "reddit": 2.0,
    "stackexchange": 2.0,
    "gitlab": 2.0,
    "hn": 1.0,
    "openalex": 1.0,
    "europepmc": 1.0,
    "bluesky": 1.0,
    "openfda": 1.0,
    "petitions": 1.0,
    "nyc311": 1.0,
}


def _provider_for_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host == "api.github.com" or host.endswith(".github.com"):
        return "github"
    if host == "api.stackexchange.com":
        return "stackexchange"
    if host == "oauth.reddit.com" or host.endswith("reddit.com"):
        return "reddit"
    if host == "gitlab.com" or host.endswith(".gitlab.com"):
        return "gitlab"
    if host == "hn.algolia.com":
        return "hn"
    if host == "api.openalex.org" or host.endswith(".openalex.org"):
        return "openalex"
    if host.endswith("europepmc.org"):
        return "europepmc"
    if host == "public.api.bsky.app":
        return "bluesky"
    if host == "api.fda.gov":
        return "openfda"
    if host.endswith("petition.parliament.uk"):
        return "petitions"
    if host == "data.cityofnewyork.us":
        return "nyc311"
    return host or "unknown"


def _bucket(provider: str, now: float) -> dict[str, float]:
    state = _REQUEST_BUCKETS.get(provider)
    if state is None:
        state = {"tokens": _REQUEST_BURST, "updated": now, "blocked_until": 0.0}
        _REQUEST_BUCKETS[provider] = state
    return state


def _take_request_budget(url: str) -> str:
    """Return an explanation if a shared call should be skipped; never sleeps or retries."""
    provider = _provider_for_url(url)
    interval = _REQUEST_INTERVALS.get(provider, 1.0)
    now = time.monotonic()
    with _REQUEST_BUDGET_LOCK:
        state = _bucket(provider, now)
        if now < state["blocked_until"]:
            return f"shared provider cooldown active for {provider}; no upstream request sent"
        elapsed = max(0.0, now - state["updated"])
        state["tokens"] = min(_REQUEST_BURST, state["tokens"] + elapsed / interval)
        state["updated"] = now
        if state["tokens"] < 1.0:
            return f"shared provider request budget depleted for {provider}; no upstream request sent"
        state["tokens"] -= 1.0
        return ""


def _cooldown_provider(url: str, retry_after: str | None) -> None:
    provider = _provider_for_url(url)
    try:
        delay = float(retry_after) if retry_after else 30.0
    except (TypeError, ValueError):
        delay = 30.0
    delay = max(1.0, min(delay, 300.0))
    now = time.monotonic()
    with _REQUEST_BUDGET_LOCK:
        state = _bucket(provider, now)
        state["blocked_until"] = max(state["blocked_until"], now + delay)
        state["tokens"] = 0.0
        state["updated"] = now


@dataclass
class Post:
    source: str
    id: str
    title: str
    text: str
    url: str
    author: str
    score: int
    comments: int
    created: str
    meta: dict = field(default_factory=dict)


@dataclass
class Result:
    posts: list
    ok: bool = True
    error: str = ""
    skipped: bool = False  # e.g. a required key is missing


def _plain(s: str | None) -> str:
    return html.unescape(TAGS.sub(" ", s or "")).strip()


def _iso(epoch) -> str:
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(float(epoch)))
    except Exception:
        return ""


def _get(url, params=None, headers=None, auth=None, method="GET", data=None):
    """Returns (json, error_string). Enforces shared provider budgets without retries."""
    budget_error = _take_request_budget(url)
    if budget_error:
        return None, budget_error
    try:
        r = httpx.request(
            method,
            url,
            params=params,
            data=data,
            auth=auth,
            headers={"User-Agent": UA, **(headers or {})},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code == 429:
            _cooldown_provider(url, r.headers.get("Retry-After"))
            return None, "rate limited (429); provider cooldown applied, no retry attempted"
        if r.status_code in (401, 403):
            return None, f"blocked or unauthorized ({r.status_code})"
        r.raise_for_status()
        return r.json(), ""
    except Exception as e:  # network, JSON, status
        return None, f"{type(e).__name__}: {str(e)[:100]}"


# ---------------------------------------------------------------- Hacker News
def hn(query: str, limit: int = 20, since_days: int = 0, **_) -> Result:  # all time: an old problem that is still unsolved still counts
    params = {"query": query, "tags": "(story,comment)", "hitsPerPage": limit}
    if since_days:
        params["numericFilters"] = f"created_at_i>{int(time.time()) - since_days * 86400}"
    data, err = _get("https://hn.algolia.com/api/v1/search", params)
    if data is None:
        return Result([], False, err)
    out = []
    for h in data.get("hits", []):
        text = _plain(h.get("comment_text") or h.get("story_text"))
        title = h.get("title") or h.get("story_title") or ""
        if not (text or title):
            continue
        oid = h.get("objectID", "")
        out.append(
            Post("hn", f"hn-{oid}", title, text, f"https://news.ycombinator.com/item?id={oid}",
                 h.get("author") or "", h.get("points") or 0, h.get("num_comments") or 0,
                 (h.get("created_at") or "")[:10])
        )
    return Result(out)


# ------------------------------------------------------------- Stack Exchange
_se_cooldown = {"until": 0.0}


def se(query: str, limit: int = 20, site: str = "superuser", **_) -> Result:
    if time.time() < _se_cooldown["until"]:
        return Result([], False, "rate limited (429); cooling down, set STACKEXCHANGE_KEY for a much larger free quota")
    params = {
        "order": "desc", "sort": "relevance", "q": query, "site": site,
        "pagesize": min(limit, 50), "filter": "withbody",
    }
    if os.environ.get("STACKEXCHANGE_KEY"):
        params["key"] = os.environ["STACKEXCHANGE_KEY"]
    data, err = _get("https://api.stackexchange.com/2.3/search/advanced", params)
    if data is None:
        if "429" in err:
            _se_cooldown["until"] = time.time() + 120  # stop hammering a limited quota
            err += "; set STACKEXCHANGE_KEY (free) for a much larger quota"
        return Result([], False, err)
    out = []
    for q in data.get("items", []):
        out.append(
            Post("se", f"se-{site}-{q.get('question_id')}", _plain(q.get("title")), _plain(q.get("body"))[:1500],
                 q.get("link") or "", (q.get("owner") or {}).get("display_name") or "",
                 q.get("score") or 0, q.get("answer_count") or 0, _iso(q.get("creation_date")),
                 {"site": site, "views": q.get("view_count") or 0, "answered": bool(q.get("is_answered"))})
        )
    return Result(out)


# --------------------------------------------------------------------- Reddit
_reddit_token = {"value": "", "exp": 0.0}
_reddit_token_lock = Lock()


def startup_request_cost(provider: str) -> int:
    """Requests needed to establish a provider session before the first data query.

    Reddit OAuth token exchange is a real HTTP request. Count it against the same
    per-call budget if credentials are configured and the in-memory token is expired.
    """
    if provider == "reddit":
        cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
        if cid and secret and not (_reddit_token["value"] and time.time() < _reddit_token["exp"]):
            return 1
    return 0


def _reddit_ua() -> dict:
    """Reddit asks for a unique, descriptive User-Agent, e.g. 'problem-radar/4.2 by u/yourname'."""
    ua = os.environ.get("REDDIT_USER_AGENT")
    return {"User-Agent": ua} if ua else {}


def _reddit_oauth() -> str:
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return ""
    # Avoid concurrent source jobs issuing duplicate token requests when the shared
    # in-memory token is missing or near expiry.
    with _reddit_token_lock:
        if _reddit_token["value"] and time.time() < _reddit_token["exp"]:
            return _reddit_token["value"]
        data, _ = _get("https://www.reddit.com/api/v1/access_token", headers=_reddit_ua(), auth=(cid, secret), method="POST",
                       data={"grant_type": "client_credentials"})
        if data and data.get("access_token"):
            _reddit_token.update(value=data["access_token"], exp=time.time() + int(data.get("expires_in", 3600)) - 60)
        return _reddit_token["value"]


def reddit(query: str, limit: int = 20, subreddit: str | None = None, sort: str = "relevance", t: str = "all", **_) -> Result:
    has_oauth_config = bool(
        os.environ.get("REDDIT_CLIENT_ID", "").strip()
        and os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    )
    token = _reddit_oauth()
    if has_oauth_config and not token:
        # Do not silently fall back to anonymous Reddit after configured OAuth fails
        # or the shared request budget blocks token acquisition.
        return Result([], False, "configured Reddit OAuth unavailable; no anonymous fallback attempted")
    params = {"q": query, "sort": sort, "t": t, "limit": min(limit, 50)}
    if subreddit:
        params["restrict_sr"] = 1
    path = f"r/{subreddit}/search" if subreddit else "search"
    if token:
        data, err = _get(f"https://oauth.reddit.com/{path}", params, {**_reddit_ua(), "Authorization": f"bearer {token}"})
    else:
        data, err = _get(f"https://www.reddit.com/{path}.json", params, _reddit_ua())
    if data is None:
        return Result([], False, err + ("" if token else " (set REDDIT_CLIENT_ID/SECRET for reliable access)"))
    out = []
    for c in (data.get("data") or {}).get("children", []):
        d = c.get("data", {})
        out.append(
            Post("reddit", f"rd-{d.get('id')}", d.get("title") or "", (d.get("selftext") or "")[:1500],
                 "https://www.reddit.com" + (d.get("permalink") or ""), d.get("author") or "",
                 d.get("score") or 0, d.get("num_comments") or 0, _iso(d.get("created_utc")),
                 {"site": d.get("subreddit") or ""})
        )
    return Result(out)


PAIN_QUERY = "problem OR struggle OR frustrating OR expensive OR wish OR hate OR annoying OR broken"


def _reddit_json(path: str, params: dict):
    token = _reddit_oauth()
    if token:
        return _get(f"https://oauth.reddit.com/{path}", params, {**_reddit_ua(), "Authorization": f"bearer {token}"})
    return _get(f"https://www.reddit.com/{path}.json", params, _reddit_ua())


def find_subreddits(query: str, want: int = 3) -> tuple[list[str], str]:
    """Communities where this topic is discussed. Their members are the people who have the problem."""
    from .pain import _has_word, content_words
    data, err = _reddit_json("subreddits/search", {"q": query, "limit": 15, "sort": "relevance"})
    if data is None:
        return [], err
    words = content_words(query)
    found = []
    for c in (data.get("data") or {}).get("children", []):
        d = c.get("data", {})
        if d.get("over18") or (d.get("subscribers") or 0) < 300:
            continue
        label = " ".join([d.get("display_name") or "", d.get("title") or ""])  # name and title only: descriptions match too loosely
        if words and not any(_has_word(w, label) for w in words):
            continue
        found.append(d.get("display_name"))
    return [f for f in found if f][:want], ""


def reddit_community(query: str, limit: int = 30, **_) -> Result:
    """Community-first Reddit: find the subreddits for a topic, then take their top complaints from the last year.
    Much less noise than searching all of Reddit, because everyone in these places already cares about the topic."""
    # One community-discovery call plus at most one community-search call: Reddit gets
    # a strict two-request budget even when a topic has many candidate communities.
    subs, err = find_subreddits(query, want=1)
    if err:
        return Result([], False, err)
    out, errs = [], []
    for sub in subs:
        res = reddit(PAIN_QUERY, limit=max(10, limit // max(len(subs), 1)), subreddit=sub, sort="top")
        if not res.ok:
            errs.append(res.error)
            continue
        from .pain import _has_word, content_words
        tight = any(_has_word(w, sub) for w in content_words(query))  # the community's own name is about the topic
        for p in res.posts:
            p.meta["community"] = "tight" if tight else "loose"
        out += res.posts
    if errs and not out:
        return Result([], False, errs[0])
    return Result(out)


# ------------------------------------------------- FDA device adverse events (openFDA, keyless)
def _readable(text: str) -> str:
    """FDA reports are mostly ALL CAPS. Make them readable: sentence case when the text is shouting."""
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        text = ". ".join(part.strip().capitalize() for part in text.lower().split(". "))
    return text


def fda_devices(query: str, limit: int = 20, **_) -> Result:
    """Real failure reports for medical and assistive devices (wheelchairs, hearing aids, prosthetics, pumps).
    Free text written by users and clinics. Unvalidated: shows that a failure happens, never how often."""
    params = {"search": f'device.generic_name:"{query}"', "limit": min(limit, 50)}
    if os.environ.get("OPENFDA_KEY"):
        params["api_key"] = os.environ["OPENFDA_KEY"]
    data, err = _get("https://api.fda.gov/device/event.json", params)
    if data is None:
        if err.startswith("HTTPStatusError") and "404" in err:
            return Result([])  # openFDA answers 404 when nothing matches
        return Result([], False, err)
    out = []
    for r in data.get("results", []):
        dev = (r.get("device") or [{}])[0]
        texts = r.get("mdr_text") or []
        event = next((t.get("text") for t in texts if "Description of Event" in (t.get("text_type_code") or "")), None) \
            or (texts[0].get("text") if texts else "")
        event = _readable(_plain(event))
        if not event:
            continue
        name = _readable(f"{dev.get('generic_name') or query} ({dev.get('brand_name') or 'unknown brand'})")
        d = r.get("date_received") or ""
        date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else ""
        out.append(Post("fda_devices", f"fda-{r.get('mdr_report_key')}", event[:120], f"{name}. {event[:1400]}",
                        f"https://api.fda.gov/device/event.json?search=mdr_report_key:{r.get('mdr_report_key')}", "",
                        0, 0, date, {"site": r.get("event_type") or "", "device": name}))
    return Result(out)


# ------------------------------------------------- Europe PMC (papers and preprints, keyless)
def europepmc(query: str, limit: int = 20, **_) -> Result:
    params = {"query": query, "format": "json", "resultType": "core", "pageSize": min(limit, 50), "sort": "CITED desc"}
    data, err = _get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params)
    if data is None:
        return Result([], False, err)
    out = []
    for r in (data.get("resultList") or {}).get("result", []):
        abstract = _plain(r.get("abstractText"))
        if not abstract:
            continue
        url = f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
        out.append(Post("europepmc", f"epmc-{r.get('source')}-{r.get('id')}", _plain(r.get("title")), abstract[:1500], url,
                        (r.get("authorString") or "")[:80], r.get("citedByCount") or 0, 0, str(r.get("pubYear") or ""),
                        {"site": "europepmc"}))
    return Result(out)


# ----------------------------------------------------- Bluesky public search
def bluesky(query: str, limit: int = 20, **_) -> Result:
    """Search public Bluesky posts via the official public AppView; no account or API key required."""
    params = {"q": query, "limit": max(1, min(int(limit), 25)), "sort": "latest"}
    data, err = _get("https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts", params)
    if data is None:
        return Result([], False, err)

    out = []
    for item in data.get("posts", []):
        record = item.get("record") or {}
        author = item.get("author") or {}
        text = _plain(record.get("text") or "")
        uri = item.get("uri") or ""
        handle = author.get("handle") or ""
        rkey = uri.rsplit("/", 1)[-1] if uri else ""
        url = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else ""
        if not text or not url:
            continue
        created = str(record.get("createdAt") or item.get("indexedAt") or "")[:10]
        out.append(Post(
            "bluesky", f"bsky-{uri}", text[:140], text[:1500], url, handle,
            int(item.get("likeCount") or 0), int(item.get("replyCount") or 0), created,
            {"site": "bluesky", "reposts": int(item.get("repostCount") or 0)},
        ))
    return Result(out)


# ----------------------------------------------------- arXiv scholarly search
_ARXIV_LOCK = Lock()
_arxiv_last_request = 0.0
_ARXIV_NS = "{http://www.w3.org/2005/Atom}"


def arxiv(query: str, limit: int = 20, **_) -> Result:
    """Search arXiv abstracts; one query at a time and at least three seconds between HTTP requests."""
    global _arxiv_last_request
    safe_query = re.sub("[^A-Za-z0-9 ._-]", " ", query)[:180].strip()
    params = {
        "search_query": f"all:{safe_query}",
        "start": 0,
        "max_results": max(1, min(int(limit), 20)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    try:
        with _ARXIV_LOCK:
            now = time.monotonic()
            if _arxiv_last_request and now - _arxiv_last_request < 3.0:
                return Result([], True, "deferred to honor arXiv's three-second request spacing; no retry attempted", skipped=True)
            try:
                response = httpx.get(
                    "https://export.arxiv.org/api/query",
                    params=params,
                    timeout=TIMEOUT,
                    headers={"User-Agent": UA},
                )
            except Exception as e:
                _arxiv_last_request = time.monotonic()
                return Result([], False, f"{type(e).__name__}: {str(e)[:80]}")
            _arxiv_last_request = time.monotonic()
    except Exception as e:
        return Result([], False, f"{type(e).__name__}: {str(e)[:80]}")

    if response.status_code == 429:
        return Result([], False, "rate limited (429); no retry attempted")
    if response.status_code >= 400:
        return Result([], False, f"arXiv HTTP {response.status_code}")
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as e:
        return Result([], False, f"invalid arXiv Atom feed: {type(e).__name__}")

    out = []
    for entry in root.findall(f"{_ARXIV_NS}entry"):
        get_text = lambda tag: " ".join((entry.findtext(f"{_ARXIV_NS}{tag}") or "").split())
        paper_id = get_text("id").replace("http://arxiv.org/abs/", "https://arxiv.org/abs/")
        title, abstract = get_text("title"), get_text("summary")
        if not paper_id or not title:
            continue
        author_el = entry.find(f"{_ARXIV_NS}author/{_ARXIV_NS}name")
        author = " ".join((author_el.text or "").split()) if author_el is not None else ""
        out.append(Post(
            "arxiv", f"arxiv-{paper_id.rsplit('/', 1)[-1]}", _plain(title), _plain(abstract)[:1500],
            paper_id, author, 0, 0, get_text("published")[:10], {"site": "arxiv"},
        ))
    return Result(out)


# ---------------------------------------------------------------------- GitLab
def gitlab(query: str, limit: int = 20, **_) -> Result:
    """Search GitLab.com issues. Requires a free read_api token; one HTTP request per query."""
    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        return Result([], True, "skipped (GITLAB_TOKEN is not configured)", skipped=True)

    data, err = _get(
        "https://gitlab.com/api/v4/search",
        {"scope": "issues", "search": query, "per_page": max(1, min(int(limit), 20))},
        {"PRIVATE-TOKEN": token},
    )
    if data is None:
        return Result([], False, err)
    if not isinstance(data, list):
        return Result([], False, "unexpected GitLab search response")

    from urllib.parse import urlparse
    out = []
    for issue in data:
        url = (issue.get("web_url") or "").strip()
        if not url.startswith("https://gitlab.com/"):
            continue
        title = _plain(issue.get("title") or "")
        description = _plain(issue.get("description") or "")
        if not (title or description):
            continue
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        project_path = "/".join(path_parts[:path_parts.index("-")]) if "-" in path_parts else ""
        author = (issue.get("author") or {}).get("username") or ""
        created = str(issue.get("created_at") or "")[:10]
        score = int(issue.get("upvotes") or 0) - int(issue.get("downvotes") or 0)
        out.append(Post(
            "gitlab", f"gl-{issue.get('id') or url}", title, description[:1500], url, author,
            score, int(issue.get("user_notes_count") or 0), created,
            {"site": project_path, "state": issue.get("state") or ""},
        ))
    return Result(out)


# --------------------------------------------------------------------- GitHub
def github(query: str, limit: int = 20, **_) -> Result:
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    data, err = _get("https://api.github.com/search/issues", {"q": f"{query} is:issue", "per_page": min(limit, 50)}, headers)
    if data is None:
        return Result([], False, err)
    out = []
    for i in data.get("items", []):
        repo = (i.get("repository_url") or "").replace("https://api.github.com/repos/", "")
        out.append(
            Post("github", f"gh-{i.get('id')}", i.get("title") or "", (i.get("body") or "")[:1500],
                 i.get("html_url") or "", (i.get("user") or {}).get("login") or "",
                 (i.get("reactions") or {}).get("total_count", 0), i.get("comments") or 0,
                 (i.get("created_at") or "")[:10], {"site": repo})
        )
    return Result(out)






# ------------------------------------------- Scholarly papers (OpenAlex, no key)
def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words: dict[int, str] = {}
    for w, positions in inv.items():
        for p in positions:
            words[p] = w
    return " ".join(words[i] for i in sorted(words))


def scholar(query: str, limit: int = 20, years: int = 4, **_) -> Result:
    """Recent OpenAlex papers. OPENALEX_API_KEY raises the free daily budget; OPENALEX_MAILTO identifies polite use."""
    since = time.strftime("%Y-01-01", time.gmtime(time.time() - years * 365 * 86400))
    params = {
        "search": query,
        "per-page": min(limit, 25),
        "filter": f"from_publication_date:{since}",
        "select": "id,doi,title,publication_year,cited_by_count,abstract_inverted_index",
    }
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    if os.environ.get("OPENALEX_MAILTO"):
        params["mailto"] = os.environ["OPENALEX_MAILTO"]
    data, err = _get("https://api.openalex.org/works", params)
    if data is None:
        return Result([], False, err)
    out = []
    for w in data.get("results", []):
        url = w.get("doi") or w.get("id") or ""
        out.append(
            Post("scholar", f"oa-{w.get('id')}", _plain(w.get("title")), _plain(_abstract(w.get("abstract_inverted_index")))[:1500],
                 url, "", w.get("cited_by_count") or 0, 0, str(w.get("publication_year") or ""), {"site": "openalex"})
        )
    return Result(out)


# ------------------------------------------- GitHub repositories (is it already built?)
def github_repos(query: str, limit: int = 15, **_) -> Result:
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    data, err = _get("https://api.github.com/search/repositories",
                     {"q": f"{query} in:name,description,readme", "sort": "stars", "order": "desc", "per_page": min(limit, 30)}, headers)
    if data is None:
        return Result([], False, err)
    out = []
    for r in data.get("items", []):
        out.append(
            Post("github_repo", f"ghr-{r.get('id')}", r.get("full_name") or "", r.get("description") or "", r.get("html_url") or "",
                 (r.get("owner") or {}).get("login") or "", r.get("stargazers_count") or 0, r.get("forks_count") or 0,
                 (r.get("pushed_at") or "")[:10], {"site": r.get("language") or "", "archived": bool(r.get("archived"))})
        )
    return Result(out)

# ------------------------------------------- Civic data (structured, no key)
def petitions(query: str, limit: int = 20, **_) -> Result:
    """UK Parliament petitions. Signature counts are quantified public demand. UK only."""
    data, err = _get("https://petition.parliament.uk/petitions.json", {"q": query, "state": "all"})
    if data is None:
        return Result([], False, err)
    out = []
    for d in (data.get("data") or [])[:limit]:
        a = d.get("attributes", {})
        pid = d.get("id")
        text = _plain(f"{a.get('background') or ''} {a.get('additional_details') or ''}")[:1500]
        out.append(
            Post("petitions", f"pet-{pid}", a.get("action") or "", text,
                 f"https://petition.parliament.uk/petitions/{pid}", "UK Parliament petition",
                 a.get("signature_count") or 0, 0, (a.get("created_at") or "")[:10],
                 {"site": "uk-petitions", "state": a.get("state") or ""})
        )
    return Result(out)


def nyc311(query: str, limit: int = 20, **_) -> Result:
    """NYC 311 complaint counts for the last 12 months, grouped by type. NYC only."""
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 3][:3]
    if not words:
        return Result([], True, "no usable keywords", skipped=True)
    since = time.strftime("%Y-%m-%dT00:00:00", time.gmtime(time.time() - 365 * 86400))
    likes = " OR ".join(
        f"upper(complaint_type) like '%{w[:5].upper()}%' OR upper(descriptor) like '%{w[:5].upper()}%'" for w in words
    )
    params = {
        "$select": "complaint_type, descriptor, count(*) as n",
        "$where": f"created_date > '{since}' AND ({likes})",
        "$group": "complaint_type, descriptor",
        "$order": "n DESC",
        "$limit": min(limit, 30),
    }
    data, err = _get("https://data.cityofnewyork.us/resource/erm2-nwe9.json", params)
    if data is None or not isinstance(data, list):
        return Result([], False, err or "unexpected response")
    out = []
    for row in data:
        ct, desc = row.get("complaint_type") or "", row.get("descriptor") or ""
        try:
            n = int(row.get("n", 0))
        except ValueError:
            n = 0
        out.append(
            Post("nyc311", f"311-{abs(hash((ct, desc)))}", f"NYC 311: {ct} / {desc}".strip(" /"),
                 f"{n} complaints filed in the last 12 months about {ct} ({desc}) in New York City.",
                 "https://data.cityofnewyork.us/resource/erm2-nwe9", "NYC 311", n, 0, "",
                 {"site": "nyc-311"})
        )
    return Result(out)

SOURCES = {"hn": hn, "se": se, "reddit": reddit, "reddit_community": reddit_community, "bluesky": bluesky, "fda_devices": fda_devices, "europepmc": europepmc, "arxiv": arxiv, "gitlab": gitlab, "github": github,
           "petitions": petitions, "nyc311": nyc311, "scholar": scholar, "github_repo": github_repos}


def enabled() -> dict:
    """What is available right now, for the source_status tool."""
    reddit_mode = "oauth" if (os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET")) else "public (often blocked on cloud hosts)"
    return {
        "scholar": {"enabled": True, "note": "OpenAlex papers; free key raises the daily budget" + (" (OPENALEX_API_KEY set)" if os.environ.get("OPENALEX_API_KEY") else "; set OPENALEX_API_KEY for the larger free daily budget") + ("; polite email set" if os.environ.get("OPENALEX_MAILTO") else "")},
        "github_repo": {"enabled": True, "note": "GitHub repository search, used by check_if_solved"},
        "petitions": {"enabled": True, "note": "UK Parliament petitions with signature counts; no key; UK only"},
        "nyc311": {"enabled": True, "note": "NYC 311 complaint counts, last 12 months; no key; NYC only"},
        "hn": {"enabled": True, "note": "no key needed"},
        "se": {"enabled": True, "note": "key optional" + (" (key set)" if os.environ.get("STACKEXCHANGE_KEY") else "; free quota is small")},
        "reddit": {"enabled": True, "note": reddit_mode},
        "bluesky": {"enabled": False, "note": "temporarily excluded from default searches after live HTTP 403 responses; re-test the public endpoint before re-enabling"},
        "arxiv": {"enabled": True, "note": "scholarly preprint search; no API key; enforces at least 3 seconds between requests"},
        "gitlab": {"enabled": bool(os.environ.get("GITLAB_TOKEN", "").strip()), "note": ("authenticated public issue search; token configured" if os.environ.get("GITLAB_TOKEN", "").strip() else "optional; set GITLAB_TOKEN with read_api scope to search public issues; no keyless global search")},
        "europepmc": {"enabled": True, "note": "Europe PMC papers and preprints (biomedical, health, some social science); no key"},
        "fda_devices": {"enabled": True, "note": "FDA device failure reports (openFDA), US; no key; set OPENFDA_KEY (free) for more quota"},
        "reddit_community": {"enabled": True, "note": "finds the subreddits for a topic, then reads their top complaints"},
        "github": {"enabled": True, "note": "token set" if os.environ.get("GITHUB_TOKEN") else "no token: low rate limit"},
    }
