"""A rolling 'what is hurting right now' feed from public sources that need no key and that we may store.

Reddit is deliberately left out: its content may not be written to disk, and this feed is saved to a file so the server can answer
instantly. A scheduled job (refresh.py pulse) rebuilds data/pulse.json; if the file is missing or old, the server builds a small
live copy instead and says so. The feed shows what people are asking or signing RIGHT NOW. It is a sample of two sources, not a
census of current problems, and it says that in its output.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import sources as S
from .pain import is_relevant, looks_like_pain
from .signal_quality import signal_profile

PULSE_FILE = Path(__file__).resolve().parent.parent / "data" / "pulse.json"
STALE_AFTER = 3 * 86400
FIRST_HAND = {"help_request", "reported_complaint", "workaround_or_manual_process", "technical_failure_report"}
_mem: dict = {"at": 0.0, "data": None}


def _hn_asks(days: int) -> tuple[list[dict], dict]:
    since = int(time.time()) - days * 86400
    data, err = S._get("https://hn.algolia.com/api/v1/search_by_date",
                       {"tags": "ask_hn", "hitsPerPage": 100, "numericFilters": f"created_at_i>{since},num_comments>=3"})
    if not isinstance(data, dict):
        return [], {"state": "failed", "error": err or "unexpected response"}
    items = []
    for h in data.get("hits", []) or []:
        title = h.get("title") or ""
        text = S._plain(h.get("story_text"))
        if not title:
            continue
        kind = signal_profile(f"{title} {text}")["evidence_kind"]
        if kind not in FIRST_HAND and not looks_like_pain(f"{title} {text}"):
            continue
        oid = h.get("objectID", "")
        items.append({"title": title[:140], "snippet": text[:220], "url": f"https://news.ycombinator.com/item?id={oid}", "source": "hn_ask",
                      "date": (h.get("created_at") or "")[:10], "signal": h.get("num_comments") or 0, "signal_is": "comments", "kind": kind,
                      "layer": "people_complaining"})
    return items, {"state": "ok", "returned": len(items)}


def _petitions() -> tuple[list[dict], dict]:
    data, err = S._get("https://petition.parliament.uk/petitions.json", {"state": "open", "page_size": 50})
    if not isinstance(data, dict):
        return [], {"state": "failed", "error": err or "unexpected response"}
    items = []
    for d in data.get("data", []) or []:
        a = d.get("attributes") or {}
        action = a.get("action") or ""
        if not action:
            continue
        items.append({"title": action[:140], "snippet": S._plain(a.get("background"))[:220], "url": f"https://petition.parliament.uk/petitions/{d.get('id')}",
                      "source": "uk_petitions", "date": (a.get("created_at") or "")[:10], "signal": a.get("signature_count") or 0,
                      "signal_is": "signatures", "kind": "official_data", "layer": "official_data"})
    items.sort(key=lambda x: -x["signal"])
    return items[:25], {"state": "ok", "returned": min(len(items), 25), "note": "UK only"}


def build(days: int = 14) -> dict:
    hn, hn_state = _hn_asks(days)
    pt, pt_state = _petitions()
    return {
        "generated_at": int(time.time()),
        "window_days": days,
        "sources": {"hn_ask": hn_state, "uk_petitions": pt_state},
        "items": sorted(hn, key=lambda x: (x["date"], x["signal"]), reverse=True) + pt,
        "what_this_is": ("A small, current sample: recent Ask HN questions that read as problems, and the most-signed open UK petitions. "
                         "It leans toward developers and the UK. It is not a census of current problems, and a topic missing here may still be real."),
    }


def save(days: int = 14) -> dict:
    data = build(days)
    PULSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PULSE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def load(days: int = 14) -> dict:
    """The saved feed if it is fresh; otherwise a live build, kept in memory for six hours."""
    try:
        if PULSE_FILE.exists():
            data = json.loads(PULSE_FILE.read_text(encoding="utf-8"))
            if time.time() - data.get("generated_at", 0) < STALE_AFTER:
                return {**data, "from": "saved_file"}
    except (OSError, ValueError):
        pass
    if _mem["data"] is None or time.time() - _mem["at"] > 6 * 3600:
        _mem.update(at=time.time(), data=build(days))
    return {**_mem["data"], "from": "live_build", "note": "the saved feed was missing or older than 3 days, so this was fetched just now"}


def find(topic: str = "", limit: int = 15) -> dict:
    data = load()
    items = data["items"]
    if topic.strip():
        items = [i for i in items if is_relevant(topic, f"{i['title']} {i['snippet']}")]
    age_days = round((time.time() - data.get("generated_at", 0)) / 86400, 1)
    return {"topic": topic, "matches": items[: max(1, min(limit, 40))], "total_matches": len(items), "feed_age_days": age_days,
            "from": data.get("from"), "window_days": data.get("window_days"), "sources": data.get("sources"), "what_this_is": data.get("what_this_is"),
            "how_to_read": ("Signals here are comments or signatures right now, not proof of demand. Use them to pick what to research, then run "
                            "research_niche on it. No match means the topic is not in this small sample, not that it is not a problem.")}
