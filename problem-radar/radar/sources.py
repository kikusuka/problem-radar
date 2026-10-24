"""Fetch raw posts from public sources. Every function returns a list of Post and never raises."""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict

import httpx

UA = {"User-Agent": "problem-radar/0.1 (open-source research tool)"}


@dataclass
class Post:
    source: str      # "hn" | "github" | "reddit"
    id: str
    title: str
    text: str
    url: str
    author: str
    score: int       # upvotes / points / reactions
    comments: int
    created: str


def _get_json(url: str, params: dict | None = None, headers: dict | None = None):
    try:
        r = httpx.get(
            url,
            params=params,
            headers={**UA, **(headers or {})},
            timeout=20,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def hn_search(query: str, limit: int = 30) -> list[Post]:
    """Hacker News via the Algolia API (no key needed)."""
    data = _get_json(
        "https://hn.algolia.com/api/v1/search",
        {"query": query, "tags": "(story,comment)", "hitsPerPage": limit},
    )
    out: list[Post] = []
    for h in (data or {}).get("hits", []):
        text = h.get("comment_text") or h.get("story_text") or ""
        title = h.get("title") or h.get("story_title") or ""
        oid = h.get("objectID", "")
        if not (text or title):
            continue
        out.append(
            Post(
                source="hn",
                id=f"hn-{oid}",
                title=title,
                text=text,
                url=f"https://news.ycombinator.com/item?id={oid}",
                author=h.get("author") or "",
                score=h.get("points") or 0,
                comments=h.get("num_comments") or 0,
                created=h.get("created_at") or "",
            )
        )
    return out


def github_issues(query: str, limit: int = 30) -> list[Post]:
    """GitHub issue search. Set GITHUB_TOKEN for higher rate limits."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = _get_json(
        "https://api.github.com/search/issues",
        {"q": f"{query} is:issue", "sort": "reactions", "order": "desc", "per_page": limit},
        headers,
    )
    out: list[Post] = []
    for i in (data or {}).get("items", []):
        out.append(
            Post(
                source="github",
                id=f"gh-{i.get('id')}",
                title=i.get("title") or "",
                text=(i.get("body") or "")[:1500],
                url=i.get("html_url") or "",
                author=(i.get("user") or {}).get("login") or "",
                score=(i.get("reactions") or {}).get("total_count", 0),
                comments=i.get("comments") or 0,
                created=i.get("created_at") or "",
            )
        )
    return out


def reddit_search(query: str, limit: int = 30, subreddit: str | None = None) -> list[Post]:
    """Reddit public JSON. Often blocked from cloud IPs; fails soft to []."""
    base = f"https://www.reddit.com/r/{subreddit}/search.json" if subreddit else "https://www.reddit.com/search.json"
    params = {"q": query, "sort": "relevance", "t": "year", "limit": limit}
    if subreddit:
        params["restrict_sr"] = 1
    data = _get_json(base, params)
    out: list[Post] = []
    for c in ((data or {}).get("data") or {}).get("children", []):
        d = c.get("data", {})
        out.append(
            Post(
                source="reddit",
                id=f"rd-{d.get('id')}",
                title=d.get("title") or "",
                text=(d.get("selftext") or "")[:1500],
                url="https://www.reddit.com" + (d.get("permalink") or ""),
                author=d.get("author") or "",
                score=d.get("score") or 0,
                comments=d.get("num_comments") or 0,
                created=str(d.get("created_utc") or ""),
            )
        )
    return out


SOURCES = {"hn": hn_search, "github": github_issues, "reddit": reddit_search}


def post_to_dict(p: Post) -> dict:
    return asdict(p)
