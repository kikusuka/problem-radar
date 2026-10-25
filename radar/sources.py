"""Source adapters. Every adapter returns a Result and never raises, so one broken source can't sink a run.

Sources (all free; keys are optional upgrades):
  hn      Hacker News via Algolia            no key
  se      Stack Exchange network             no key (STACKEXCHANGE_KEY raises the daily quota)
  reddit  Reddit                             public JSON often blocked from cloud IPs;
                                             set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET for reliable OAuth access
  github  GitHub issues                      GITHUB_TOKEN recommended
  petitions  UK Parliament petitions         no key; signature counts show public demand (UK only)
  nyc311     NYC 311 complaints              no key; complaint counts by type (NYC only)
"""
from __future__ import annotations

import html
import os
import re
import time
from dataclasses import dataclass, field

import httpx

UA = "problem-radar/0.2 (open-source research tool)"
TIMEOUT = 12.0
TAGS = re.compile(r"<[^>]+>")


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
    """Returns (json, error_string)."""
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
            return None, "rate limited (429)"
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


def _reddit_ua() -> dict:
    """Reddit asks for a unique, descriptive User-Agent, e.g. 'problem-radar/4.2 by u/yourname'."""
    ua = os.environ.get("REDDIT_USER_AGENT")
    return {"User-Agent": ua} if ua else {}


def _reddit_oauth() -> str:
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return ""
    if _reddit_token["value"] and time.time() < _reddit_token["exp"]:
        return _reddit_token["value"]
    data, _ = _get("https://www.reddit.com/api/v1/access_token", headers=_reddit_ua(), auth=(cid, secret), method="POST",
                   data={"grant_type": "client_credentials"})
    if data and data.get("access_token"):
        _reddit_token.update(value=data["access_token"], exp=time.time() + int(data.get("expires_in", 3600)) - 60)
    return _reddit_token["value"]


def reddit(query: str, limit: int = 20, subreddit: str | None = None, sort: str = "relevance", t: str = "all", **_) -> Result:
    token = _reddit_oauth()
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
    subs, err = find_subreddits(query)
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


# ------------------------------------------------- DuckDuckGo (best-effort fallback, no key)
_ddg_cooldown = {"until": 0.0}
DDG_ENTRY = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', re.S)


def _ddg_url(href: str) -> str:
    """DuckDuckGo wraps links as //duckduckgo.com/l/?uddg=<encoded url>. Unwrap them."""
    from urllib.parse import parse_qs, unquote, urlparse
    href = html.unescape(href)
    if "uddg=" in href:
        q = parse_qs(urlparse(href if "//" in href else "//" + href).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    return ("https:" + href) if href.startswith("//") else href


def ddg(query: str, limit: int = 10, **_) -> Result:
    """DuckDuckGo HTML results. NO official API exists: this reads a public page, which DuckDuckGo may block or disallow,
    especially from a shared server IP. It is a last-resort fallback: it backs off for 10 minutes when blocked and
    never raises. Results are web pages (not complaints), so treat them as leads to verify."""
    if os.environ.get("DISABLE_DDG") == "1":
        return Result([], True, "disabled (DISABLE_DDG=1)", skipped=True)
    if time.time() < _ddg_cooldown["until"]:
        return Result([], False, "blocked or rate limited; cooling down")
    try:
        r = httpx.post("https://html.duckduckgo.com/html/", data={"q": query}, timeout=TIMEOUT,
                       headers={"User-Agent": "Mozilla/5.0 (compatible; problem-radar/0.2)"})
    except Exception as e:
        return Result([], False, f"{type(e).__name__}: {str(e)[:80]}")
    if r.status_code in (202, 403, 429) or "anomaly" in r.text[:3000].lower():
        _ddg_cooldown["until"] = time.time() + 600
        return Result([], False, f"blocked or rate limited ({r.status_code})")
    if r.status_code != 200:
        return Result([], False, f"HTTP {r.status_code}")
    out = []
    for href, title, snippet in DDG_ENTRY.findall(r.text)[:limit]:
        url = _ddg_url(href)
        domain = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        out.append(Post("ddg", f"ddg-{url}", re.sub(r"\s+", " ", _plain(title)), re.sub(r"\s+", " ", _plain(snippet)), url, domain, 0, 0, "", {"site": domain}))
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
    """Recent papers from OpenAlex. Set OPENALEX_MAILTO for the faster polite pool."""
    since = time.strftime("%Y-01-01", time.gmtime(time.time() - years * 365 * 86400))
    params = {
        "search": query,
        "per-page": min(limit, 25),
        "filter": f"from_publication_date:{since}",
        "select": "id,doi,title,publication_year,cited_by_count,abstract_inverted_index",
    }
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

SOURCES = {"hn": hn, "se": se, "reddit": reddit, "reddit_community": reddit_community, "fda_devices": fda_devices, "europepmc": europepmc, "ddg": ddg, "github": github,
           "petitions": petitions, "nyc311": nyc311, "scholar": scholar, "github_repo": github_repos}


def enabled() -> dict:
    """What is available right now, for the source_status tool."""
    reddit_mode = "oauth" if (os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET")) else "public (often blocked on cloud hosts)"
    return {
        "scholar": {"enabled": True, "note": "OpenAlex papers; no key" + ("" if os.environ.get("OPENALEX_MAILTO") else "; set OPENALEX_MAILTO for faster access")},
        "github_repo": {"enabled": True, "note": "GitHub repository search, used by check_if_solved"},
        "petitions": {"enabled": True, "note": "UK Parliament petitions with signature counts; no key; UK only"},
        "nyc311": {"enabled": True, "note": "NYC 311 complaint counts, last 12 months; no key; NYC only"},
        "hn": {"enabled": True, "note": "no key needed"},
        "se": {"enabled": True, "note": "key optional" + (" (key set)" if os.environ.get("STACKEXCHANGE_KEY") else "; free quota is small")},
        "reddit": {"enabled": True, "note": reddit_mode},
        "ddg": {"enabled": os.environ.get("DISABLE_DDG") != "1", "note": "DuckDuckGo page fallback, best effort and used only when results are thin; may be blocked from a shared IP"},
        "europepmc": {"enabled": True, "note": "Europe PMC papers and preprints (biomedical, health, some social science); no key"},
        "fda_devices": {"enabled": True, "note": "FDA device failure reports (openFDA), US; no key; set OPENFDA_KEY (free) for more quota"},
        "reddit_community": {"enabled": True, "note": "finds the subreddits for a topic, then reads their top complaints"},
        "github": {"enabled": True, "note": "token set" if os.environ.get("GITHUB_TOKEN") else "no token: low rate limit"},
    }
