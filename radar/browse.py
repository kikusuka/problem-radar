"""Browse mode: what are people stuck on right now, with no topic needed.

research_niche answers "what is wrong with X". This answers "what is wrong, lately", optionally inside a broad area
("money", "school", "work"). It searches complaint phrasings over the last weeks, keeps first-hand posts only, and splits
them into separate problems by the phrases people share. A small current sample, not a census, and it says so."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from . import research as R
from . import sources as S
from .ratelimit import limiter

_CACHE: dict = {}
TTL = 6 * 3600
PHRASES = ["frustrated with", "is there a way to", "why is there no", "wish there was", "struggling with", "can't believe how hard"]


def _one(q: str, t: str) -> list:
    """Posts for one Reddit query, or None when it could not run (rate limited or failed), so the caller can say so."""
    if not limiter.take("reddit", 1 + S.startup_request_cost("reddit")):
        return None
    try:
        res = S.reddit(q, limit=40, sort="top", t=t)
        return res.posts if res.ok else None
    except Exception:
        return None


def _hn(area: str) -> list:
    if not limiter.take("hn", 1):
        return None
    try:
        res = S.hn(f"{area} problem" if area else "ask hn how do you deal with", limit=20, since_days=45)
        return res.posts if res.ok else None
    except Exception:
        return None


def find(area: str = "", days: int = 30, limit: int = 20, region: str = "") -> dict:
    area = (area or "").strip()[:80]
    key = (area.casefold(), days, region.casefold())
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return {**hit[1], "from_cache": True}
    t = "week" if days <= 7 else "month" if days <= 45 else "year"
    where = f" {region}" if region else ""
    queries = [f"{area} {p}{where}".strip() for p in PHRASES[:4]]
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(_one, q, t) for q in queries] + [ex.submit(_hn, area)]
        results = [f.result() for f in futs]
    failed = sum(1 for r in results if r is None)
    posts = [p for r in results if r for p in r]
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - max(days, 7) * 86400))
    seen, kept = set(), []
    for p in posts:
        if p.id in seen or not p.title or (p.created or "9999")[:10] < cutoff:
            continue
        seen.add(p.id)
        sub = (p.meta.get("site") or "").casefold()
        if sub in R.VIRAL_SUBREDDITS or R._is_thin(p) or R._is_outreach(p) or R._is_pitch(p.title):
            continue
        if R._is_prospective(p) and not R._first_person(p):
            continue
        if p.source.startswith("reddit") and not (R._first_person(p) or p.comments >= 3):
            continue
        kept.append(p)
    kept.sort(key=lambda p: p.score + 2 * p.comments, reverse=True)
    cands = [(float(p.score + 2 * p.comments), p, "") for p in kept[:60]]
    themes = R._complaint_themes(cands, [area] if area else [], n=8)
    posts_out = [{"id": f"c{i}", "title": p.title, "snippet": (p.text or "")[:220], "url": p.url, "source": f"{p.source}/{p.meta.get('site')}" if p.meta.get("site") else p.source,
                  "date": (p.created or "")[:10], "score": p.score, "comments": p.comments} for i, (_, p, _) in enumerate(cands[:max(5, min(limit, 40))], 1)]
    out = {
        "area": area or "(anything)", "window_days": days, "posts_seen": len(posts), "posts_kept": len(kept),
        "problem_groups": themes,
        "posts": posts_out,
        "what_this_is": ("A current sample of first-hand complaints from Reddit and Hacker News, gathered with complaint phrasings and filtered to posts where "
                         "someone describes their own trouble. problem_groups split them by phrases several different authors share; they are hints, "
                         "so read the posts and group by meaning. It is not a census: it over-represents English-speaking, online people. "
                         "Next: research_niche on a group's topic to dig in, check_if_solved before calling it a gap, and plan conversations with affected people."),
        "generated_at": int(time.time()),
    }
    out["searches"] = {"run": len(results) - failed, "failed_or_rate_limited": failed}
    if failed:
        out["warning"] = f"{failed} of {len(results)} searches did not run (rate limit or the source was unavailable), so this sample is smaller than usual. Try again in a minute."
    if len(kept) < 5:
        out["thin"] = "Few posts qualified. Try a broader area, a longer window, or leave the area empty."
    if not failed:  # a partial result must not be cached for hours
        _CACHE[key] = (time.time(), out)
    return out
