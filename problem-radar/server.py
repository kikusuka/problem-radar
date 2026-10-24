"""Problem Radar MCP server.

Local (stdio, for Claude Desktop / Claude Code):   python server.py
Hosted (HTTP, for Render / HF Spaces / etc.):      TRANSPORT=streamable-http PORT=8000 python server.py
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from radar import store

mcp = FastMCP(
    "problem-radar",
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
)

WRITE_UP = (
    "For each card, write: (1) a one-line problem statement, (2) who has it, (3) what they do manually today, "
    "(4) what it costs them, (5) a weekend-MVP scope. Use ONLY the evidence provided and cite the evidence URLs. "
    "Do not invent facts. Drop any card whose evidence does not actually describe a real problem."
)


def _trim(card: dict, full: bool = False) -> dict:
    out = {
        "id": card["id"],
        "topic_terms": card["topic_terms"],
        "post_count": card["post_count"],
        "scores": card["scores"],
        "evidence": card["evidence"] if full else card["evidence"][:3],
    }
    return out


@mcp.tool()
def find_problems(niche: str, limit: int = 8, refresh: bool = False, sources: list[str] | None = None) -> dict:
    """Find real, evidence-backed problems people complain about in a niche (e.g. "accounting", "shopify stores").

    Mines Hacker News, GitHub issues and Reddit for pain phrases, clusters repeated complaints, and ranks them.
    Only clusters with 3+ posts from 2+ independent authors are returned. Results are cached for 24h.
    Set refresh=True to force a live re-mine. sources can be any of: hn, github, reddit.
    """
    data = store.get_or_refresh(niche, force=refresh, sources=sources)
    cards = data["cards"][: max(1, min(limit, 25))]
    return {
        "niche": niche,
        "posts_scanned": data["posts_scanned"],
        "returned": len(cards),
        "cards": [_trim(c) for c in cards],
        "instructions_for_llm": WRITE_UP,
        "note": "" if cards else "No verified clusters. Try a broader niche or refresh=True.",
    }


@mcp.tool()
def get_problem(problem_id: str) -> dict:
    """Get the full card for one problem id: all evidence links, snippets and score breakdown."""
    card = store.find_card(problem_id)
    if not card:
        return {"error": f"No problem with id {problem_id}. Run find_problems first."}
    return {**_trim(card, full=True), "niche": card["niche"], "instructions_for_llm": WRITE_UP}


@mcp.tool()
def hackathon_ideas(theme: str, limit: int = 10) -> dict:
    """Turn a hackathon theme or brief into problem statements grounded in real complaints.

    Mines the theme, returns the top clusters, and tells the LLM how to shape each into a pitch.
    """
    data = store.get_or_refresh(theme)
    cards = data["cards"][: max(1, min(limit, 25))]
    return {
        "theme": theme,
        "cards": [_trim(c, full=True) for c in cards],
        "instructions_for_llm": WRITE_UP
        + " Then add a 2-sentence hackathon pitch and a 24-hour build plan for each. "
        "Prefer problems that fit the theme and can be demoed in 3 minutes.",
    }


@mcp.tool()
def save_problem(problem_id: str, note: str = "") -> dict:
    """Save a problem to the backlog so you can come back to it. Optional note."""
    card = store.find_card(problem_id)
    if not card:
        return {"error": f"No problem with id {problem_id}."}
    items = store.save_to_backlog(card, note)
    return {"saved": problem_id, "backlog_size": len(items)}


@mcp.tool()
def list_backlog() -> dict:
    """List saved problems, best score first."""
    items = sorted(store.read_backlog(), key=lambda c: c["scores"]["overall"], reverse=True)
    return {"count": len(items), "items": [{**_trim(i), "niche": i["niche"], "note": i.get("note", "")} for i in items]}


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("TRANSPORT", "stdio"))
