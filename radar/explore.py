"""The 'lens': what makes this different from a web search.

A web search returns pages for one query. Problem finding is a loop: look wide, notice how the people who have the problem
actually talk, go where they talk, read what they say in the comments, and check what is missing. These helpers turn one
result into guidance for the next step, using only what was actually found (no fixed lists, no LLM in the server).
Every function takes plain dicts, so it is easy to test.
"""
from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from .cluster import clean, keywords
from .text import has_unspaced, tokens

LAYERS = {
    "people_complaining": "people describing the problem in their own words",
    "builders_working_on_it": "people building or discussing a fix (repos, issues)",
    "official_data": "official or measured data (petitions, complaint counts, device reports)",
    "research_interest": "papers that call it open or understudied",
}
READABLE_HOSTS = ("news.ycombinator.com", "www.reddit.com", "reddit.com", "old.reddit.com")


def people_say(views: list[dict], niche: str, searched: list[str], n: int = 8) -> list[str]:
    """Words and word pairs that recur across different posts and are not already in the query: the community's own vocabulary."""
    skip = keywords(" ".join([niche, *searched]))
    df: Counter = Counter()
    # Words from posts only loosely about the topic (a car-accident claim for a crop-insurance search) would send the next search off-topic.
    on_topic = [v for v in views if v.get("topic_in") == "title"]
    for v in (on_topic if len(on_topic) >= 4 else views):
        body = clean(f"{v['title']} {v['snippet']}")
        toks = re.findall(r"[a-z][a-z0-9\-\+#]{2,}", body.lower()) if body.isascii() else [t for t in tokens(body) if len(t) > 2 or has_unspaced(t)]
        uni = {t for t in toks if t in keywords(t) and t not in skip}
        bi = {f"{a} {b}" for a, b in zip(toks, toks[1:]) if a in uni and b in uni}
        df.update(uni | bi)
    ranked = [(t, c) for t, c in df.items() if c >= 2]
    ranked.sort(key=lambda x: (-(x[1] * (1.8 if " " in x[0] else 1.0)), x[0]))
    out: list[str] = []
    for t, _ in ranked:
        if " " not in t and any(t in o.split() for o in out):
            continue  # a single word already covered by a chosen pair
        out.append(t)
        if len(out) == n:
            break
    return out


def communities(views: list[dict], n: int = 6) -> list[dict]:
    """Where the discussion happens. Each is a place to search again, or to read, with search_pain."""
    counts: Counter = Counter(v["source"] for v in views if "/" in v["source"])
    return [{"where": w, "posts": c} for w, c in counts.most_common(n) if c >= 2]


def gaps(views: list[dict], layer_of: dict[str, str], region_note: str = "") -> list[dict]:
    """Which kinds of evidence were NOT found, and what to do about each. Absence here is a reason to look, not proof."""
    present = {layer_of.get(v["source"].split("/")[0]) for v in views}
    todo = {
        "builders_working_on_it": "run check_if_solved to see whether anything already addresses it",
        "official_data": "no official or measured data surfaced; " + (region_note or "look for regulator, ministry or statistics-office data with your own web search"),
        "research_interest": "run find_research_gaps for papers that call it open",
    }
    return [{"missing": k, "meaning": LAYERS[k], "do": todo[k]} for k in todo if k not in present]


def readable(view: dict) -> bool:
    host = urlparse(view.get("url", "")).netloc.lower()
    return host in READABLE_HOSTS and not view.get("promotional")


def next_moves(views: list[dict], clusters: list[dict], vocab: list[str], comms: list[dict], gap_list: list[dict],
               niche: str, lens: str, region: str = "", limit: int = 6) -> list[dict]:
    """Concrete next tool calls, in priority order. The LLM decides which to run."""
    moves: list[dict] = []
    pool = [v for v in views if readable(v) and v.get("comments", 0) >= 5]
    # A big thread only helps if it is about the topic: prefer threads with the topic in the title over merely busy ones.
    pool = [v for v in pool if v.get("topic_in") == "title"] or pool
    threads = sorted(pool, key=lambda v: -v["comments"])
    for v in threads[:2]:
        moves.append({"tool": "read_thread", "args": {"url": v["url"]},
                      "why": f"{v['comments']} comments: the detail (who pays, what they tried, what failed) is in the replies, not the headline"})
    picked: list[str] = []
    for phrase in vocab:  # distinct searches: skip a phrase that shares a word with one already chosen
        if len(picked) == 2:
            break
        if any(set(phrase.split()) & set(p.split()) for p in picked):
            continue
        picked.append(phrase)
    for phrase in picked:
        moves.append({"tool": "search_pain", "args": {"query": phrase},
                      "why": "this is how people in these results talk about it; search their words, not yours"})
    for c in comms[:1]:
        if c["where"].startswith("reddit/"):
            moves.append({"tool": "search_pain", "args": {"query": niche, "subreddit": c["where"].split("/", 1)[1]},
                          "why": f"{c['posts']} results came from {c['where']}: go deeper where these people already gather"})
    strong = next((c for c in clusters if c["evidence_strength"] in ("strong", "moderate")), None)
    moves.append({"tool": "check_if_solved", "args": {"problem": (strong["label"] if strong else niche), "lens": lens if lens != "any" else "software"},
                  "why": "before calling it a gap, see whether something already solves it"})
    for g in gap_list:
        if g["missing"] == "research_interest" and lens in ("research", "any"):
            moves.append({"tool": "find_research_gaps", "args": {"topic": niche}, "why": g["do"]})
            break
    return moves[:limit]


def comment_flags(text: str) -> dict:
    """Cheap, honest cues in one comment. They point at lines worth reading; they are not conclusions."""
    from .pain import HACK_WORDS
    from .research import PAYMENT_EVIDENCE, PAYMENT_INTENT, PAYMENT_NEGATION
    t = text or ""
    return {
        "mentions_payment": bool(PAYMENT_EVIDENCE.search(t) and not PAYMENT_NEGATION.search(t)),
        "would_pay": bool(PAYMENT_INTENT.search(t) and not PAYMENT_NEGATION.search(t)),
        "workaround": bool(HACK_WORDS.search(t)),
        "asks_for_solution": bool(re.search(r"\b(is there|does anyone know|any (?:app|tool|service|way)|looking for|(?:can|could) (?:anyone|someone) recommend|any recommendations?|recommend(?:ations?)? (?:for|a|an)\b)", t, re.I)),
    }
