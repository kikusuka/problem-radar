"""Mine a niche end to end and keep results in plain JSON files (no database needed)."""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .cluster import build_cards, clean
from .pain import signals
from .pain import build_queries, looks_like_pain
from .sources import SOURCES, post_to_dict

DATA = Path(__file__).resolve().parent.parent / "data"
CARDS_DIR = DATA / "cards"
BACKLOG = DATA / "backlog.json"
MAX_AGE = 24 * 3600


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "niche"


def mine(niche: str, sources: list[str] | None = None, per_query: int = 25) -> list[dict]:
    """Run every pain query against every source in parallel; keep pain-looking, de-duplicated posts."""
    names = [s for s in (sources or list(SOURCES)) if s in SOURCES]
    jobs = [(SOURCES[s], q) for s in names for q in build_queries(niche)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda j: j[0](j[1], per_query), jobs))
    seen, posts = set(), []
    for batch in results:
        for p in batch:
            d = post_to_dict(p)
            if d["id"] in seen:
                continue
            seen.add(d["id"])
            if looks_like_pain(f"{d['title']} {d['text']}"):
                posts.append(d)
    return posts


def refresh(niche: str, sources: list[str] | None = None) -> dict:
    posts = mine(niche, sources)
    def heat(p):
        s = signals(clean(f"{p['title']} {p['text']}"))
        return s["pain"] + s["hack"] + 2 * s["money"] + p["score"] * 0.1 + p["comments"] * 0.2

    top = sorted(posts, key=heat, reverse=True)[:8]
    payload = {
        "niche": niche,
        "generated_at": int(time.time()),
        "posts_scanned": len(posts),
        "cards": build_cards(posts, niche),
        "weak_signals": [
            {"url": p["url"], "source": p["source"], "title": p["title"], "snippet": clean(p["text"] or p["title"])[:240]}
            for p in top
        ],
    }
    if payload["cards"]:
        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        (CARDS_DIR / f"{slug(niche)}.json").write_text(json.dumps(payload, indent=2))
    return payload


def load(niche: str, max_age: int = MAX_AGE) -> dict | None:
    f = CARDS_DIR / f"{slug(niche)}.json"
    if not f.exists():
        return None
    payload = json.loads(f.read_text())
    if time.time() - payload.get("generated_at", 0) > max_age:
        return None
    return payload


def get_or_refresh(niche: str, force: bool = False, sources: list[str] | None = None) -> dict:
    if not force:
        cached = load(niche)
        if cached:
            return cached
    return refresh(niche, sources)


def find_card(card_id: str) -> dict | None:
    for f in CARDS_DIR.glob("*.json"):
        for c in json.loads(f.read_text()).get("cards", []):
            if c["id"] == card_id:
                return c
    return None


def read_backlog() -> list[dict]:
    return json.loads(BACKLOG.read_text()) if BACKLOG.exists() else []


def save_to_backlog(card: dict, note: str = "") -> list[dict]:
    items = [i for i in read_backlog() if i["id"] != card["id"]]
    items.append({**card, "note": note, "saved_at": int(time.time())})
    DATA.mkdir(parents=True, exist_ok=True)
    BACKLOG.write_text(json.dumps(items, indent=2))
    return items
