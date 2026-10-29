"""A small, hand-sourced library of problem statements that organisers have published (competitions, challenges).

What this is: problems someone with authority wrote down and asked students to solve. What it is NOT: evidence that people want
a solution, that the problem is unsolved, or that it is still open. Every entry carries where it came from; nothing is generated.
Use research_niche / check_if_solved / validate_problem to test an entry before building on it.
"""
from __future__ import annotations

from pathlib import Path

from . import text as _text
from .pain import STOP_WORDS

DATA = Path(__file__).resolve().parent.parent / "data"

SOURCES = {
    "sih2025": {
        "event": "Smart India Hackathon 2025", "year": 2025, "kind": "government and industry problem statements",
        "url": "https://www.sih.gov.in/sih2025PS",
        "provenance": "Copied from a printout of the official problem-statement page dated 2025-08-31 (hosted by a college), then obvious scan typos fixed "
                      "(e.g. 'lmage' to 'Image'). Very long titles end where the printout cut them. Check sih.gov.in for the full text and the current year.",
        "files": "sih2025.txt",
    },
    "nasa2025": {
        "event": "NASA International Space Apps Challenge 2025", "year": 2025, "kind": "NASA subject-matter-expert challenges",
        "url": "https://www.spaceappschallenge.org/2025/challenges/",
        "provenance": "Titles only, taken from a university news page listing 19 challenges (the official page did not render a list for me). "
                      "'Create Your Own Challenge' is left out because it is not a problem statement. "
                      "Read the full challenge statement on spaceappschallenge.org before choosing one.",
        "files": "nasa_space_apps_2025.txt",
    },
}

_cache: list[dict] | None = None


def _load() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache
    rows: list[dict] = []
    for key, meta in SOURCES.items():
        path = DATA / meta["files"]
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            if key == "sih2025":
                pid, title, org, theme, kind = (line.split("|") + [""] * 5)[:5]
                rows.append({"id": pid, "title": title, "organiser": org, "theme": theme, "kind": kind, "source": key})
            else:
                rows.append({"id": "NASA25-%02d" % (len(rows) + 1), "title": line, "organiser": "NASA", "theme": "", "kind": "", "source": key})
    _cache = rows
    return rows


def _words(s: str) -> set[str]:
    return {w for w in _text.tokens(s) if w not in STOP_WORDS and (len(w) > 2 or _text.has_unspaced(w))}


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 4 and w.endswith("s") else w


def find(topic: str = "", kind: str = "", source: str = "", limit: int = 12) -> dict:
    """Rank library entries by how many of the topic's words appear in title, theme or organiser. Empty topic lists entries."""
    q = {_stem(w) for w in _words(topic)}
    rows = []
    for r in _load():
        if source and r["source"] != source:
            continue
        if kind and r["kind"] and r["kind"] != kind.lower():
            continue
        hay = {_stem(w) for w in _words(f"{r['title']} {r['theme']} {r['organiser']}")}
        title_hay = {_stem(w) for w in _words(r["title"])}
        hits = q & hay
        if q and not hits:
            continue
        # every topic word found beats a partial match; a hit in the title beats a hit in the theme
        score = (len(hits) / len(q) if q else 0.0) * 2 + len(q & title_hay) / max(len(q), 1)
        rows.append((score, r))
    rows.sort(key=lambda x: (-x[0], x[1]["id"]))
    if q and any(sc >= 2 for sc, _ in rows):  # some entries contain every topic word: show only those, not the partial matches
        rows = [x for x in rows if x[0] >= 2]
    out = []
    for score, r in rows[: max(1, min(limit, 40))]:
        meta = SOURCES[r["source"]]
        out.append({**{k: v for k, v in r.items() if v}, "event": meta["event"], "year": meta["year"], "url": meta["url"]})
    return {
        "topic": topic,
        "matches": out,
        "total_matches": len(rows),
        "libraries": {k: {"event": v["event"], "entries": sum(1 for r in _load() if r["source"] == k), "provenance": v["provenance"]} for k, v in SOURCES.items()},
        "how_to_read": ("These are problems an organiser wrote down for students. They are not evidence that people want a solution, that nothing "
                        "solves it already, or that it is still open this year. Check with check_if_solved, then research_niche or validate_problem "
                        "on the best one or two. Entries older than the current year may be closed or re-issued."),
    }
