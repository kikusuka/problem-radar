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
def hn(query: str, limit: int = 20, since_days: int = 730, **_) -> Result:
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
def se(query: str, limit: int = 20, site: str = "superuser", **_) -> Result:
    params = {
        "order": "desc", "sort": "relevance", "q": query, "site": site,
        "pagesize": min(limit, 50), "filter": "withbody",
    }
    if os.environ.get("STACKEXCHANGE_KEY"):
        params["key"] = os.environ["STACKEXCHANGE_KEY"]
    data, err = _get("https://api.stackexchange.com/2.3/search/advanced", params)
    if data is None:
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


def reddit(query: str, limit: int = 20, subreddit: str | None = None, **_) -> Result:
    token = _reddit_oauth()
    params = {"q": query, "sort": "relevance", "t": "year", "limit": min(limit, 50)}
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

SOURCES = {"hn": hn, "se": se, "reddit": reddit, "github": github,
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
        "github": {"enabled": True, "note": "token set" if os.environ.get("GITHUB_TOKEN") else "no token: low rate limit"},
    }
