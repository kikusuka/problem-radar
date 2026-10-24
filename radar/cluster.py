"""Cluster posts by topic overlap and score the clusters. Pure Python, no LLM, no heavy deps.

The user's own LLM (Claude etc.) does the final writing. We only do the cheap, deterministic part:
group repeats, count independent voices, and rank.
"""
from __future__ import annotations

import hashlib
import html
import re
from collections import Counter

from .pain import signals

STOP = set(
    """a an the and or but if then so of to in on for with at by from as is are was were be been being it its this that
these those i you he she we they me my your our their do does did done have has had can could should would will just
not no yes very really about into out up down over under more most some any all how what why when where who which
there here than too also get got make made use used using like want need one two
tool tools manually manual tired waste wasting hours hour every week weekly anyone know looking way ways free time work works
thing things people think wish automate automatically automation help please thanks hey anyone else still maybe actually
something someone everyone currently different better best good great new old many much even back going gets getting
study studies data results result methods method conducted review analysis background objective objectives purpose paper papers
research findings approach proposed show shows shown present presents however although within across among between several
different various main including related recent current novel significant effect effects based role overall aim aims
introduction conclusion conclusions participants""".split()
)
TOKEN = re.compile(r"[a-z][a-z0-9\-\+#\.]{2,}")
TAGS = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    return html.unescape(TAGS.sub(" ", text or "")).strip()


def keywords(text: str, extra_stop: set[str] | None = None) -> set[str]:
    stop = STOP | (extra_stop or set())
    return {t for t in TOKEN.findall(text.lower()) if t not in stop}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


MIN_SHARED = 3


def cluster_posts(posts: list[dict], niche: str, threshold: float = 0.3) -> list[list[dict]]:
    """Greedy clustering. posts are dicts (see sources.Post)."""
    niche_tokens = keywords(niche)
    items = []
    seen = set()
    for p in posts:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        body = clean(f"{p['title']} {p['text']}")
        kw = keywords(body, niche_tokens)
        if len(kw) < 4:
            continue
        items.append((p, kw))

    # Single-link: a post joins the cluster holding its most similar member,
    # if they share enough specific terms. (A growing union made the old version far too strict.)
    clusters: list[dict] = []  # {"members": [(post, kw)], "posts": [..]}
    for p, kw in items:
        best, best_sim = None, 0.0
        for c in clusters:
            for _, mkw in c["members"]:
                shared = len(kw & mkw)
                if shared < MIN_SHARED:
                    continue
                sim = shared / min(len(kw), len(mkw))
                if sim > best_sim:
                    best, best_sim = c, sim
        if best is not None and best_sim >= threshold:
            best["members"].append((p, kw))
            best["posts"].append(p)
        else:
            clusters.append({"members": [(p, kw)], "posts": [p]})
    return [c["posts"] for c in clusters]


def top_terms(cluster: list[dict], niche: str, n: int = 6) -> list[str]:
    niche_tokens = keywords(niche)
    counts: Counter = Counter()
    for p in cluster:
        counts.update(keywords(clean(f"{p['title']} {p['text']}"), niche_tokens))
    return [w for w, _ in counts.most_common(n)]


def _scale(x: float, full: float) -> float:
    return round(min(x / full, 1.0) * 10, 1)


def score_cluster(cluster: list[dict]) -> dict:
    authors = {p["author"] for p in cluster if p["author"]}
    sources = {p["source"] for p in cluster}
    sig = {"money": 0, "hack": 0, "pain": 0}
    for p in cluster:
        s = signals(clean(f"{p['title']} {p['text']}"))
        for k in sig:
            sig[k] += s[k]
    engagement = sum(p["score"] + 2 * p["comments"] for p in cluster)

    frequency = _scale(len(authors), 6)
    pain = _scale(sig["pain"] + sig["hack"] + 2 * sig["money"], 12)
    engage = _scale(engagement, 200)
    diversity = _scale(len(sources), 3)
    overall = round(0.4 * frequency + 0.3 * pain + 0.2 * engage + 0.1 * diversity, 1)

    # Evidence rule: no card without 3+ posts from 2+ independent authors.
    verified = len(cluster) >= 3 and len(authors) >= 2
    return {
        "overall": overall,
        "frequency": frequency,
        "pain": pain,
        "engagement": engage,
        "source_diversity": diversity,
        "signals": sig,
        "independent_authors": len(authors),
        "verified": verified,
    }


def make_card(cluster: list[dict], niche: str) -> dict:
    terms = top_terms(cluster, niche)
    cid = hashlib.sha1((niche + "|" + ",".join(sorted(terms))).encode()).hexdigest()[:10]
    ranked = sorted(cluster, key=lambda p: p["score"] + 2 * p["comments"], reverse=True)
    evidence = [
        {
            "url": p["url"],
            "source": p["source"],
            "title": p["title"],
            "snippet": clean(p["text"] or p["title"])[:280],
            "score": p["score"],
        }
        for p in ranked[:6]
    ]
    return {
        "id": cid,
        "niche": niche,
        "topic_terms": terms,
        "post_count": len(cluster),
        "scores": score_cluster(cluster),
        "evidence": evidence,
    }


def build_cards(posts: list[dict], niche: str, min_posts: int = 3) -> list[dict]:
    cards = [make_card(c, niche) for c in cluster_posts(posts, niche) if len(c) >= min_posts]
    cards = [c for c in cards if c["scores"]["verified"]]
    cards.sort(key=lambda c: c["scores"]["overall"], reverse=True)
    return cards
