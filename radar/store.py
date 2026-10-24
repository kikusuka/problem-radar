"""Personal data kept in plain JSON: a backlog of problems you chose, and your own friction log.

These tools are off on the hosted server (ENABLE_PERSONAL unset) because the files would be shared by every visitor.
Turn them on for local use with ENABLE_PERSONAL=1.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
BACKLOG = DATA / "backlog.json"
FRICTION = DATA / "friction.json"


def _read(path: Path) -> list[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def _write(path: Path, items: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2))


def save_problem(title: str, statement: str, evidence_urls: list[str], note: str = "") -> dict:
    items = [i for i in _read(BACKLOG) if i["title"].lower() != title.lower()]
    items.append({"title": title, "statement": statement, "evidence_urls": evidence_urls, "note": note,
                  "saved_at": int(time.time())})
    _write(BACKLOG, items)
    return {"saved": title, "backlog_size": len(items)}


def list_backlog() -> list[dict]:
    return sorted(_read(BACKLOG), key=lambda i: i["saved_at"], reverse=True)


def log_friction(note: str, tags: list[str] | None = None) -> dict:
    items = _read(FRICTION)
    items.append({"note": note, "tags": tags or [], "at": int(time.time())})
    _write(FRICTION, items)
    return {"logged": True, "total": len(items)}


def search_friction(query: str = "") -> list[dict]:
    items = _read(FRICTION)
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    if not words:
        return items[-50:]
    return [i for i in items if any(w in (i["note"] + " " + " ".join(i["tags"])).lower() for w in words)]
