"""Problem Radar MCP server (v5).

Local (stdio, for Claude Desktop / Claude Code):   python server.py
Hosted (HTTP, for Render / Northflank / etc.):     TRANSPORT=streamable-http python server.py

Finds problems worth solving: software, hardware, policy and research, for students, makers, teams and citizens. The server does wide, relevant retrieval and
honest coverage reporting; the LLM you chat with does the judging.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from radar import brief, hunt, library, pulse, research, solved, sources, store, verify

INSTRUCTIONS = (
    "Problem Radar is a problem-finding lens, not a web search: it finds what people struggle with, in their own words, and shows how much "
    "evidence stands behind it and what is missing. You do the judging; it fetches and checks. Follow these stages. "
    "1 ORIENT (pick a direction): student_hunt or plan_hunt if the person is unsure; whats_happening for what is live now; "
    "find_known_problems for problems hackathons already published. "
    "2 DISCOVER: research_niche (pass region and local wording in `also`); read `candidates` yourself and group them by meaning. "
    "3 DIG: follow `next_moves`: read_thread (the detail is in the replies), search_pain with the words in `people_say`, drill into `communities`. "
    "4 TEST: check_if_solved, then validate_problem for the best two or three. Existing products are supply, not proof of demand. "
    "5 DELIVER: write a brief in the shape of radar://brief, label each piece of evidence DOCUMENTED (official, measured or paper source) or "
    "HYPOTHESIS (public posts only), say who is not heard, then run check_brief and fix what it flags before answering. "
    "Results are public posts, not a survey; absence of results is not proof a problem does not exist."
)

mcp = FastMCP(
    "problem-radar",
    instructions=INSTRUCTIONS,
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
)


PRIVACY = (
    "Problem Radar privacy: the server keeps no accounts and stores no personal data. Search terms you send are used to query "
    "public sources (Hacker News, Reddit, Stack Exchange, GitHub, GitLab, arXiv, OpenAlex, Europe PMC, openFDA and public "
    "government datasets) and results may be cached on the server for up to 36 hours (Reddit content is held in memory only, never written to disk). Usernames of post authors are never returned."
)
TERMS = (
    "Problem Radar terms: free, read-only research aid provided as is, without warranty. Results are public posts and records; "
    "check them yourself before relying on them. Do not use it to target or harass individuals."
)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "problem-radar"})


@mcp.custom_route("/privacy", methods=["GET"])
async def privacy(request: Request) -> PlainTextResponse:
    return PlainTextResponse(PRIVACY)


@mcp.custom_route("/terms", methods=["GET"])
async def terms(request: Request) -> PlainTextResponse:
    return PlainTextResponse(TERMS)


@mcp.tool(title="Plan a problem hunt", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def plan_hunt(goal: str = "general", interests: list[str] | None = None, skills: list[str] | None = None,
              hours: str = "", budget: str = "", lens: str = "any", location: str = "") -> dict:
    """START HERE when the person is unsure what to search. Turns their situation into a research plan.

    goal: hackathon, hobby, portfolio, impact or general. skills: e.g. ["python", "arduino"]. interests: e.g. ["elderly care"].
    lens: software, hardware, policy or any (inferred from skills if left as any). Returns the fix type to hunt for,
    seed niches to research, the steps to follow, and a fit rubric that scores problems for THIS person, not just by pain.
    """
    return hunt.plan_hunt(goal, interests, skills, hours, budget, lens, location)


@mcp.tool(title="Student problem hunt", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def student_hunt(level: str = "undergraduate", field: str = "", goal: str = "class_project", weeks: float = 8,
                 team_size: int = 1, interests: list[str] | None = None, resources: str = "", location: str = "") -> dict:
    """START HERE for students: finds a project that fits your level, field, time and goal.

    level: high school, undergraduate, masters or phd. goal: class_project, capstone, hackathon, research, science_fair
    or general. weeks: time you have (a hackathon weekend is 0.3). Returns the fix type to hunt for, scope guardrails
    sized to your time, seed niches (including campus and student life), a student rubric that weights feasibility
    for YOU, ethics notes, and the steps to follow.
    """
    return hunt.student_hunt(level, field, goal, weeks, team_size, interests, resources, location)


@mcp.tool(title="What people are asking right now", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def whats_happening(topic: str = "", limit: int = 15) -> dict:
    """A rolling feed of current problems: recent Ask HN questions that read as problems, and the most-signed open UK petitions.
    Use it to see what is live right now or to pick a topic before research_niche. topic filters it; empty shows everything.
    It is a small current sample (developers and the UK lean), refreshed daily by a scheduled job, not a census. No match
    does not mean a topic is not a problem. The result says how old the feed is and whether it was fetched just now."""
    return pulse.find(topic, limit)


@mcp.tool(title="Check a finished problem brief", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def check_brief(brief_json: dict) -> dict:
    """Last step before you answer. Pass your finished brief as an object with: statement, who, workaround, evidence (a list of
    {claim, url, label}), already_solved, who_is_missing, validation_plan, kill_criteria. Reports missing fields, links this server
    never returned, claims the cited text does not support, and public posts wrongly labelled DOCUMENTED. Read radar://brief for
    the full shape. ok=true means the brief is complete and its citations match, not that the problem is real."""
    return brief.check(brief_json)


@mcp.resource("radar://brief")
def brief_resource() -> str:
    """The shape of a finished problem brief and the rules for labelling evidence."""
    import json
    return json.dumps(brief.SCHEMA, indent=1)


@mcp.resource("radar://pulse")
def pulse_resource() -> str:
    """The current rolling feed of problems people are asking about right now."""
    import json
    return json.dumps(pulse.load(), indent=1, ensure_ascii=False)


@mcp.tool(title="Find problems organisers have published", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def find_known_problems(topic: str = "", kind: str = "", limit: int = 12) -> dict:
    """Problem statements that hackathons and challenges have already published (Smart India Hackathon 2025, NASA Space Apps 2025).

    Good for a student who needs a scoped, buildable starting point fast. topic: a few words ("water", "crop advisory", "rural
    education"); empty lists entries. kind: software or hardware (SIH entries are tagged). Each entry names its event, year and
    organiser and links to the official page. These are what an organiser asked for, NOT proof that people want it or that it is
    unsolved or still open: follow with check_if_solved and research_niche before building. Works offline from a fixed list.
    """
    return library.find(topic, kind, limit=limit)


@mcp.tool(title="Check if a problem is already solved", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def check_if_solved(problem: str, lens: str = "software") -> dict:
    """Is this problem already solved? Checks existing projects, products, papers and public actions before you commit.

    Searches GitHub repositories, Show HN and product discussion, and recent papers; policy checks also use UK petitions.
    The research lens adds arXiv preprints. It gives a hint with reasons and a guide to finding the gap the best existing
    solution leaves open. Absence of results is never proof that nobody solved it. If required_constraints are present, candidates must demonstrate those constraints;
    constraint_candidates_excluded counts related candidates that did not; constraint_near_misses shows up to five topical
    candidates that match the topic but do not demonstrate every hard constraint. related_candidates separately shows
    partial topic matches with missing_topic_anchors, even when the candidate uses a neighboring term such as "LLM runner"
    instead of "assistant". Those are inspection leads only: they do not count as existing solutions or make the verdict
    "partially solved". Generic word overlap is not enough to qualify a lead.
    "inconclusive_constraints_not_matched" or "inconclusive_related_candidates" means the search did not establish a full fit,
    not that no solution exists. lens: software, hardware, policy, research or any.
    """
    return solved.check(problem, lens)


@mcp.tool(title="Find research gaps", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def find_research_gaps(topic: str, depth: str = "quick", limit: int = 25, refresh: bool = False) -> dict:
    """For theses, papers and science projects: finds recent papers that call something open, understudied or future work.

    Same as research_niche with lens=research and goal=research. Abstracts are the evidence; check novelty with
    check_if_solved before committing.
    """
    return research.research(topic, depth, limit, force=refresh, lens="research", goal="research")


@mcp.tool(title="Explore problem domains", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def explore_domains(interest: str = "") -> dict:
    """Seed ideas for people with no starting point: life and work domains with concrete niches to research.

    Optionally filter by a word like "health", "city" or "kids".
    """
    return hunt.explore_domains(interest)


@mcp.tool(title="Research a niche for real problems", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def research_niche(niche: str, lens: str = "any", goal: str = "general", depth: str = "quick", limit: int = 25,
                   refresh: bool = False, sources: list[str] | None = None, se_sites: list[str] | None = None,
                   also: list[str] | None = None, region: str = "") -> dict:
    """Research a niche for real, recurring problems. Returns a wide pool of public-source leads for YOU to judge.

    Read `candidates` (up to 50 short, lightly filtered posts: id, title, snippet, url, source, date, kind) and decide
    yourself which are really about the topic and which describe a concrete, repeated problem. `problem_clusters` groups
    candidates by shared theme with voices, sources, years and a confidence label; treat them as hints. `top_posts` is a
    stricter keyword-filtered subset. Counts are clues, not proof: results are public posts, not a survey, and a missing
    result is not evidence that a problem does not exist. Check `coverage` before interpreting thin results.

    region: leave empty for worldwide. If the person mentions a place ("I'm in India", "UK problems"), pass a country name
    or code. That adds the country's communities and name to the searches and uses official data where it exists (UK
    petitions, NYC 311, US FDA reports). Other places have community and paper coverage only, and the result says so. For
    non-English or local wording, pass local terms in `also`.
    also: up to four synonyms or related terms. Never drop hard requirements from the niche (offline, low-resource,
    affordable, platform); results missing them appear as near_misses.
    lens: software, hardware, policy, research, or any (default). goal: hackathon, hobby, portfolio, impact, class_project,
    capstone, research, science_fair. depth: quick or deep. se_sites: Stack Exchange sites. sources: override the default
    sources. Cached 36h; refresh=True re-runs. Searches are budgeted per provider and rate-limited across all users; the
    coverage block says when a source was partial or rate_limited.
    """
    return research.research(niche, depth, limit, sources, se_sites, force=refresh, lens=lens, goal=goal, also=also, region=region)


@mcp.tool(title="Search complaints and pain points", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def search_pain(query: str, sources: list[str] | None = None, limit: int = 20, subreddit: str | None = None,
                se_sites: list[str] | None = None) -> dict:
    """Search for complaints with your own wording, e.g. 'pedestrian crossing near school' or 'quickbooks invoice export'.

    Use it to follow up on a theme from research_niche or probe a specific workflow. Pass subreddit to focus Reddit.
    Built-in sources only: there is no automatic general web-search fallback. Results require topical and pain/workaround
    evidence; product-launch announcements and spending-only mentions are not treated as independent complaints.
    Query constraints are surfaced in each result's missing_constraints field rather than silently discarding every
    related complaint that omits a constraint. Query length is capped and source/site lists are bounded; per-provider
    request limits may omit planned work. Check coverage and treat results as leads.
    """
    return research.search(query, sources, limit, subreddit, se_sites)


@mcp.tool(title="Read a thread's comments", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def read_thread(url: str, limit: int = 30) -> dict:
    """Read the comments of one Hacker News or Reddit thread from a result's url. The real evidence (who pays, what they tried,
    what failed) is usually in the replies, not the headline. Comments are flagged for payment, workaround and solution requests
    as cues to read, not proof. Authors are never returned. Count distinct people, not comments."""
    return research.read_thread(url, limit)


@mcp.tool(title="Check claims against the evidence", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def check_claims(claims: list[dict]) -> dict:
    """Before you answer, check your key claims against what this server actually retrieved. Pass a list of
    {"claim": "<one sentence>", "urls": ["<url you cite>"]}. For each claim it reports whether the URL was really returned by this
    server (catches invented links), whether the numbers in the claim appear in the text, and the sentence that best supports it.
    Statuses: supported_by_text, partly_supported, not_found_in_text, url_not_retrieved. Lexical check, not a judge of meaning:
    read anything that is not supported_by_text, and fix or drop what it flags."""
    return verify.check_claims(claims)


@mcp.tool(title="Validate a problem", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def validate_problem(problem: str, niche: str = "", lens: str = "software") -> dict:
    """Check a candidate problem before building or campaigning: existing solutions, willingness-to-pay signals and workarounds.

    Pass a short description. lens software, hardware or policy changes what counts as an existing solution
    (products, devices, laws, petitions). Read evidence_status and evidence_note first: insufficient_evidence means
    the search found no qualifying evidence, not that no solution or demand exists; limited_evidence means coverage
    or evidence volume is thin; evidence_found_needs_validation means public leads were found but do not validate demand.
    paying_signals are relevant spending/price mentions; willingness_to_pay_signals require explicit positive intent to pay;
    workaround_signals must refer to the target problem. Follow the validation guide and talk to real users.
    """
    return research.validate(problem, niche, lens)


@mcp.tool(title="Hackathon problem ideas", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def hackathon_ideas(theme: str, lens: str = "software", limit: int = 25, depth: str = "quick", region: str = "") -> dict:
    """Ground a hackathon theme in real complaints. Same as research_niche with goal=hackathon. region: country, or empty for worldwide."""
    return research.research(theme, depth, limit, lens=lens, goal="hackathon", region=region)


@mcp.tool(title="Source status and coverage", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


if os.environ.get("ENABLE_PERSONAL") == "1" and os.environ.get("TRANSPORT", "stdio") != "stdio":
    raise RuntimeError("ENABLE_PERSONAL is for local stdio use only; disable it for HTTP transports.")

@mcp.resource("radar://method")
def method_resource() -> str:
    """How Problem Radar judges evidence: what counts as demand, what is only a hint, and what it cannot see."""
    from pathlib import Path
    f = Path(__file__).parent / "docs" / "METHOD.md"
    return f.read_text(encoding="utf-8") if f.exists() else INSTRUCTIONS


@mcp.prompt()
def find_problems(topic: str, region: str = "") -> str:
    """Step-by-step way to turn research_niche output into a few honest problem statements."""
    return (
        f"Find real, unsolved problems in: {topic}" + (f" (region: {region})" if region else "") + ".\n"
        "1. Call research_niche. Judge `candidates` yourself; clusters and strength labels are hints, not verdicts.\n"
        "2. For each promising problem, name the evidence: who complains, what workaround they use, and whether anyone pays.\n"
        "3. Call check_if_solved. Existing products are supply, not proof of demand.\n"
        "4. Invert the claim: if an official or company source says it is solved, search for users reporting that it is not.\n"
        "5. Look for gaps between places: solved in one region, broken in another.\n"
        "6. Use read_thread on the best threads and check_claims on your final statements.\n"
        "7. Label every statement DOCUMENTED (cited) or HYPOTHESIS. Say who is not heard (representation_risk). Do not invent scores."
    )


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("TRANSPORT", "stdio"))
