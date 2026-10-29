"""Check an answer's claims against the text the server actually retrieved.

Deep-research agents are often wrong about their own citations (an independent audit found citation accuracy of roughly
50-80% and many statements with no support in the cited sources). The server keeps every post and comment it has returned,
so it can answer, deterministically: was this URL really retrieved, do the numbers in the claim appear in it, and which
sentence best supports the claim. It is a lexical check, not a judge of meaning; it catches invented links, invented
numbers and claims that no retrieved text mentions. The LLM and the person still read what it flags.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from threading import Lock

from .cluster import clean
from .pain import content_words, relevance

MAX_ITEMS = 4000
MAX_TEXT = 4000
_index: "OrderedDict[str, dict]" = OrderedDict()
_lock = Lock()
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")


def _norm(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def remember(url: str, title: str = "", text: str = "", source: str = "", date: str = "") -> None:
    """Record what was retrieved for a URL. Later calls for the same URL add text (e.g. comments read afterwards)."""
    key = _norm(url)
    if not key:
        return
    with _lock:
        row = _index.pop(key, None) or {"url": url, "title": "", "text": "", "source": source, "date": date}
        row["title"] = row["title"] or title
        if text and text[:200] not in row["text"]:
            row["text"] = (row["text"] + " " + text).strip()[:MAX_TEXT]
        _index[key] = row
        while len(_index) > MAX_ITEMS:
            _index.popitem(last=False)


def remember_posts(posts) -> None:
    for p in posts:
        remember(p.url, p.title, clean(p.text or ""), p.source, p.created)


def remember_payload(payload: dict) -> None:
    """Re-register results served from the cache (the index is in memory and empty after a restart)."""
    for key in ("candidates", "top_posts", "near_misses"):
        for item in payload.get(key, []) or []:
            remember(item.get("url", ""), item.get("title", ""), item.get("snippet", ""), item.get("source", ""), item.get("date", ""))


WORD_NUMBERS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
                "ten": "10", "eleven": "11", "twelve": "12", "hundred": "100", "thousand": "1000"}
WORD_RX = re.compile(r"\b(" + "|".join(WORD_NUMBERS) + r")\b", re.I)


def numbers(text: str) -> set[str]:
    """Numbers in a text, with small number words ("six months") counted as digits so a paraphrase is not called invented."""
    t = text or ""
    found = {re.sub(r"[,\s%]", "", m.group(0)) for m in NUMBER.finditer(t)}
    return found | {WORD_NUMBERS[m.group(1).lower()] for m in WORD_RX.finditer(t)}


def check_claim(claim: str, urls: list[str]) -> dict:
    claim = clean(claim)[:500]
    need_numbers = numbers(claim)
    words = content_words(claim)
    results = []
    for url in urls[:5]:
        row = _index.get(_norm(url))
        if row is None:
            results.append({"url": url, "retrieved": False, "status": "url_not_retrieved",
                            "note": "this server never returned this link; it may be invented or from another tool. Open it yourself or drop it."})
            continue
        body = clean(f"{row['title']}. {row['text']}")
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", body) if s]
        best, best_rel = "", 0.0
        for s in sentences or [body]:
            r = relevance(claim, s) if words else 0.0
            if r > best_rel:
                best, best_rel = s, r
        have = numbers(body)
        missing = sorted(need_numbers - have)
        if not words:
            status = "unchecked"
        elif best_rel >= 0.6 and not missing:
            status = "supported_by_text"
        elif best_rel >= 0.3 or (best_rel >= 0.2 and not need_numbers):
            status = "partly_supported"
        else:
            status = "not_found_in_text"
        entry = {"url": url, "retrieved": True, "status": status, "overlap": round(best_rel, 2)}
        if best:
            entry["best_sentence"] = best[:240]
        if missing:
            entry["numbers_not_in_source"] = missing
        results.append(entry)
    order = ["supported_by_text", "partly_supported", "unchecked", "not_found_in_text", "url_not_retrieved"]
    best_status = min((r["status"] for r in results), key=order.index) if results else "no_citation"
    return {"claim": claim, "status": best_status, "citations": results}


def check_claims(claims: list[dict]) -> dict:
    if not isinstance(claims, list) or not claims:
        raise ValueError("claims must be a non-empty list of {claim, urls}")
    out = []
    for c in claims[:20]:
        if not isinstance(c, dict) or not isinstance(c.get("claim"), str):
            raise ValueError("each claim needs a 'claim' string and a 'urls' list")
        urls = c.get("urls") or []
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            raise ValueError("'urls' must be a list of strings")
        out.append(check_claim(c["claim"], urls))
    tally: dict[str, int] = {}
    for r in out:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    return {
        "claims": out,
        "summary": tally,
        "note": ("Lexical check against text this server retrieved: it catches invented links, invented numbers and claims no retrieved text mentions. "
                 "It cannot judge meaning. Read anything not 'supported_by_text'. 'url_not_retrieved' is expected for pages you read yourself with other "
                 "tools (official sites, papers): this server cannot check those, so confirm them against the page. "
                 "A claim with no citation, or backed only by posts, is a HYPOTHESIS."),
    }
