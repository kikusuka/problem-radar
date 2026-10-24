"""Problem Radar MCP server (v4).

Local (stdio, for Claude Desktop / Claude Code):   python server.py
Hosted (HTTP, for Render / Northflank / etc.):     TRANSPORT=streamable-http python server.py

Finds problems worth solving: software, hardware, policy and research, for students, makers, teams and citizens. The server does wide, relevant retrieval and
honest coverage reporting; the LLM you chat with does the judging.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from radar import hunt, research, solved, sources, store

mcp = FastMCP(
    "problem-radar",
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
)


@mcp.tool()
def plan_hunt(goal: str = "general", interests: list[str] | None = None, skills: list[str] | None = None,
              hours: str = "", budget: str = "", lens: str = "any", location: str = "") -> dict:
    """START HERE when the person is unsure what to search. Turns their situation into a research plan.

    goal: hackathon, hobby, portfolio, impact or general. skills: e.g. ["python", "arduino"]. interests: e.g. ["elderly care"].
    lens: software, hardware, policy or any (inferred from skills if left as any). Returns the fix type to hunt for,
    seed niches to research, the steps to follow, and a fit rubric that scores problems for THIS person, not just by pain.
    """
    return hunt.plan_hunt(goal, interests, skills, hours, budget, lens, location)


@mcp.tool()
def student_hunt(level: str = "undergraduate", field: str = "", goal: str = "class_project", weeks: float = 8,
                 team_size: int = 1, interests: list[str] | None = None, resources: str = "", location: str = "") -> dict:
    """START HERE for students: finds a project that fits your level, field, time and goal.

    level: high school, undergraduate, masters or phd. goal: class_project, capstone, hackathon, research, science_fair
    or general. weeks: time you have (a hackathon weekend is 0.3). Returns the fix type to hunt for, scope guardrails
    sized to your time, seed niches (including campus and student life), a student rubric that weights feasibility
    for YOU, ethics notes, and the steps to follow.
    """
    return hunt.student_hunt(level, field, goal, weeks, team_size, interests, resources, location)


@mcp.tool()
def check_if_solved(problem: str, lens: str = "software") -> dict:
    """Is this problem already solved? Checks existing projects, products, papers and public actions before you commit.

    Searches GitHub repositories (software), Show HN and product discussion, recent papers, and UK petitions (policy),
    then gives a hint (well served, partially solved, no clear solution found) with reasons and a guide to finding the
    gap the best existing solution leaves open. Absence of results is never proof that nobody solved it.
    lens: software, hardware, policy, research or any.
    """
    return solved.check(problem, lens)


@mcp.tool()
def find_research_gaps(topic: str, depth: str = "quick", limit: int = 25, refresh: bool = False) -> dict:
    """For theses, papers and science projects: finds recent papers that call something open, understudied or future work.

    Same as research_niche with lens=research and goal=research. Abstracts are the evidence; check novelty with
    check_if_solved before committing.
    """
    return research.research(topic, depth, limit, force=refresh, lens="research", goal="research")


@mcp.tool()
def explore_domains(interest: str = "") -> dict:
    """Seed ideas for people with no starting point: life and work domains with concrete niches to research.

    Optionally filter by a word like "health", "city" or "kids".
    """
    return hunt.explore_domains(interest)


@mcp.tool()
def research_niche(niche: str, lens: str = "any", goal: str = "general", depth: str = "quick", limit: int = 25,
                   refresh: bool = False, sources: list[str] | None = None, se_sites: list[str] | None = None) -> dict:
    """Research a niche for real, recurring problems.

    lens picks where and how to search: software (tools, automation), hardware (devices, DIY, products),
    policy (rules, services, civic fixes; includes UK petition signature counts and NYC 311 complaint counts),
    research (recent papers calling something open or understudied), or any (default; the analyst decides the fix type).
    goal tunes the guidance: hackathon, hobby, portfolio, impact, class_project, capstone, research, science_fair.
    Returns the most relevant complaints with links, recurring themes, rough groupings, and a coverage report saying
    which sources worked, failed or were skipped. Posts are raw and unverified: group by meaning, discard noise,
    and follow the analysis_guide. depth: quick (default) or deep. sources: any of hn, se, reddit, github, web, petitions,
    nyc311, scholar. se_sites: Stack Exchange site names, e.g. ["electronics", "diy"]. Cached 36h; refresh=True re-runs.
    """
    return research.research(niche, depth, limit, sources, se_sites, force=refresh, lens=lens, goal=goal)


@mcp.tool()
def search_pain(query: str, sources: list[str] | None = None, limit: int = 20, subreddit: str | None = None,
                se_sites: list[str] | None = None) -> dict:
    """Search for complaints with your own wording, e.g. 'pedestrian crossing near school' or 'quickbooks invoice export'.

    Use it to follow up on a theme from research_niche, probe a specific workflow, or cover a gap when a source failed
    or the place is outside the built-in civic data. Pass subreddit to focus Reddit.
    """
    return research.search(query, sources, limit, subreddit, se_sites)


@mcp.tool()
def validate_problem(problem: str, niche: str = "", lens: str = "software") -> dict:
    """Check a candidate problem before building or campaigning: existing solutions, willingness-to-pay signals and workarounds.

    Pass a short description. lens software, hardware or policy changes what counts as an existing solution
    (products, devices, laws, petitions) and adds fix-specific checks. Posts alone never prove demand, so it also
    tells you what to ask real people.
    """
    return research.validate(problem, niche, lens)


@mcp.tool()
def hackathon_ideas(theme: str, lens: str = "software", limit: int = 25, depth: str = "quick") -> dict:
    """Ground a hackathon theme in real complaints. Same as research_niche with goal=hackathon."""
    return research.research(theme, depth, limit, lens=lens, goal="hackathon")


@mcp.tool()
def source_status() -> dict:
    """Show which sources are active and which optional keys are missing, so you know the search coverage."""
    return {"sources": sources.enabled(),
            "personal_tools": "on" if os.environ.get("ENABLE_PERSONAL") == "1" else "off (set ENABLE_PERSONAL=1 locally)"}


if os.environ.get("ENABLE_PERSONAL") == "1":  # local use only; on a hosted server these files are shared by everyone

    @mcp.tool()
    def save_problem(title: str, statement: str, evidence_urls: list[str], note: str = "") -> dict:
        """Save a problem you picked to your backlog, with its evidence links."""
        return store.save_problem(title, statement, evidence_urls, note)

    @mcp.tool()
    def list_backlog() -> dict:
        """List saved problems, newest first."""
        items = store.list_backlog()
        return {"count": len(items), "items": items}

    @mcp.tool()
    def log_friction(note: str, tags: list[str] | None = None) -> dict:
        """Record something annoying from your own day. Your friction log is a source nobody else has."""
        return store.log_friction(note, tags)

    @mcp.tool()
    def search_friction(query: str = "") -> dict:
        """Search your friction log (empty query returns the latest entries)."""
        items = store.search_friction(query)
        return {"count": len(items), "items": items}


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("TRANSPORT", "stdio"))
