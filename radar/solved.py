"""Is this problem already solved? Looks across existing projects, products, papers and public actions.

Most "does it exist?" checks only look at software repos. A problem can also be solved by a product on a shelf,
a paper that already answers the question, or a rule that already exists, so we look at all of them and say what
each source can and cannot show. The verdict is a hint, and it is honest about when the search was too thin to say.

Tested live: a long, specific problem sentence matched almost nothing, producing a false "no solution found".
So we search short keyword variants, and treat thin evidence as "inconclusive", never as "unsolved".
"""
from __future__ import annotations

import re
import time

from . import sources as S
from .pain import constraints_match, missing_constraints, query_variants, relevance, topic_fit, topic_core_query
from .research import MAX_QUERY_CHARS, Job, _body, _compact, _dedupe, run_jobs, web_suggestions

SOLUTION_RE = re.compile(
    r"\b(alternative|alternatives|saas|plugin|extension|startup|launched|i built|we built|show hn|open[- ]source|app that|"
    r"tool called|product|device|gadget|kit|kickstarter|sells|service)\b",
    re.I,
)

GAP_ANGLES = (
    "If the problem is partly solved, the opening is usually WHO or WHAT the best solution leaves out: price, language, "
    "platform, region, age, disability, offline use, simplicity, privacy, or a specific niche or workflow. Read the best "
    "solution's open issues, reviews and complaints for the gap. Pick one angle and say what you would do differently. "
    "If it is well solved, say so honestly and suggest contributing to the leader, serving an unserved segment, or choosing another problem."
)
HARDWARE_CAVEAT = (
    "Physical products are mostly invisible to these sources (they index code, discussion and papers, not shops). "
    "Before concluding anything, search retail sites and maker marketplaces yourself, and ask people who have the problem."
)


def _days_since(date: str) -> int | None:
    try:
        return int((time.time() - time.mktime(time.strptime(date[:10], "%Y-%m-%d"))) / 86400)
    except Exception:
        return None


def _recent(date: str, days: int) -> bool:
    d = _days_since(date)
    return d is not None and d < days


def _project(p: S.Post) -> dict:
    return {
        "name": p.title,
        "url": p.url,
        "description": (p.text or "")[:200],
        "stars": p.score,
        "last_push": p.created,
        "archived": bool(p.meta.get("archived")),
        "language": p.meta.get("site", ""),
    }


def assess(projects: list[dict], papers: list[dict], actions: list[dict], lens: str, discussion: list[dict] | None = None,
           raw_count: int = 0, sources_ok: int = 0) -> dict:
    discussion = discussion or []
    reasons = []
    strong = [p for p in projects if p["stars"] >= 1000 and not p["archived"] and _recent(p["last_push"], 540)]
    some = [p for p in projects if 50 <= p["stars"] < 1000 and not p["archived"]]
    cited = [p for p in papers if p["score"] >= 50]
    won = [a for a in actions if a["score"] >= 10000]

    if strong:
        reasons.append(f"{len(strong)} actively maintained project(s) with 1000+ stars, e.g. {strong[0]['name']}")
    if some:
        reasons.append(f"{len(some)} smaller project(s) with 50-999 stars")
    if cited:
        reasons.append(f"{len(cited)} well-cited recent paper(s) on this topic")
    if won:
        reasons.append(f"{len(won)} public petition(s) with 10,000+ signatures, so it is already on the public agenda")

    # A paper or petition can be relevant context without demonstrating that a usable
    # solution exists. Only implementation/project evidence or concrete product
    # discussion can support the "partially solved" hint outside the research lens.
    solution_evidence = bool(projects or discussion)
    related_context = bool(papers or actions)
    caveat = ("Absence here is not proof nobody has solved it: these sources skew English and online, and your wording may "
              "differ from theirs. Try other wording with search_pain, other languages and regions, and ask people.")
    if lens == "hardware":
        caveat = HARDWARE_CAVEAT + " " + caveat

    if strong or (lens == "research" and len(cited) >= 3):
        hint = "well_served_for_the_general_case"
    elif solution_evidence:
        hint = "partially_solved"
        if not reasons:
            reasons.append("some related implementation or product discussion exists, but its strength and fit remain uncertain")
    elif lens == "hardware":
        hint = "inconclusive_products_not_covered"
        reasons.append("nothing found that demonstrates a matching solution, but physical products are not fully covered by these sources")
    elif raw_count < 15 or sources_ok < 2:
        hint = "inconclusive_search_too_thin"
        reasons.append(f"only {raw_count} raw results from {sources_ok} working source(s); too little to conclude anything")
    else:
        hint = "no_clear_solution_found"
        if related_context:
            reasons.append("Related research papers or public actions were found, but they do not by themselves demonstrate a working solution matching the requested constraints.")
        else:
            reasons.append("searched several sources with short keyword variants and found no clearly relevant solution")
    return {"hint": hint, "reasons": reasons, "is_a_hint_only": True, "caveat": caveat}


def _solution_search_queries(problem: str, lens: str) -> list[str]:
    """Search the core subject before strict requirements, then validate constraints on candidates.

    Repo metadata and product descriptions often omit resource details. Keeping the subject
    query broad enough discovers candidate solutions; missing requirements become explicit
    near-misses rather than disappearing before the user can inspect them.
    """
    core = topic_core_query(problem)
    platform_match = re.search(r"\b(android|ios|iphone|ipad|windows|linux|macos|chromeos)\b", problem, re.I)
    platform = platform_match.group(1) if platform_match else ""
    has_model = bool(re.search(
        r"\b(?:ai|llms?|slms?|language models?|llama(?:\.cpp)?|ollama|gguf|qwen|mistral|gemma)\b",
        problem, re.I,
    ))
    has_assistant = bool(re.search(
        r"\b(?:assistant|chatbot|chat bot|voice assistant|voice chat|conversational agent)\b",
        problem, re.I,
    ))
    candidates: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip(" ,;:")
        if value and value.casefold() not in {q.casefold() for q in candidates}:
            candidates.append(value)

    if platform and core:
        add(f"{platform} {core}")
    if has_model:
        add(f"{platform} local LLM" if platform else "local LLM")
    if has_assistant:
        add(f"{platform} AI chatbot" if platform else "AI chatbot")
    if core:
        add(core)
    # Keep one constraint-rich query as a final candidate for source coverage/reporting.
    strict = query_variants(problem)
    for query in strict:
        add(query)
    return candidates[:4]


def check(problem: str, lens: str = "software") -> dict:
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("problem must be a non-empty string")
    problem = problem.strip()
    if len(problem) > MAX_QUERY_CHARS:
        raise ValueError(f"problem must be at most {MAX_QUERY_CHARS} characters")
    lens = lens if lens in ("software", "hardware", "policy", "research", "any") else "software"
    variants = query_variants(problem)
    solution_queries = _solution_search_queries(problem, lens)
    jobs: list[Job] = []

    # One distinct query per provider slot. Previously the first two HN slots were
    # "Show HN X" and "X alternative"—near duplicates that wasted half the budget.
    hn_queries = solution_queries[:2]
    for index, query in enumerate(hn_queries):
        jobs.append(Job("hn", f"Show HN {query}" if index == 0 else query, {}, 20))
    if lens in ("software", "any", "hardware"):
        for query in solution_queries[:2]:
            jobs.append(Job("github_repo", query if lens != "hardware" else f"{query} open source", {}, 15))
    if lens in ("software", "research", "any", "hardware"):
        # Broad topic query plus the compact constraint-rich query; the paper source
        # must not consume both calls on only a long, overly restrictive description.
        scholar_queries = list(dict.fromkeys([*solution_queries[:1], *(variants[:1])]))
        for query in scholar_queries[:2]:
            jobs.append(Job("scholar", query, {}, 15))
    if lens == "research" and solution_queries:
        jobs.append(Job("arxiv", solution_queries[0], {}, 15))
    if lens == "hardware":
        for query in solution_queries[:2]:
            jobs.append(Job("reddit", f"{query} diy", {}, 15))
    if lens == "policy":
        for query in solution_queries[:2]:
            jobs.append(Job("petitions", query, {}, 15))
            jobs.append(Job("reddit", f"{query} law OR policy OR campaign", {}, 15))

    raw, status = run_jobs(jobs)

    topic_queries = list(dict.fromkeys([*solution_queries, *variants]))
    projects, discussion, papers, actions = [], [], [], []
    constraint_mismatch_count = 0
    constraint_near_misses: list[tuple[float, dict]] = []
    for p in _dedupe(raw):
        text = _body(p)
        matching_queries = [
            query for query in topic_queries
            if topic_fit(query, text, p.title)
        ]
        if not matching_queries:
            continue
        rel = max((relevance(query, text) for query in matching_queries), default=0.0)
        if rel < 0.35:
            continue

        # Subject match and requirements fit are deliberately separate. A relevant
        # project that omits low-RAM or offline details is not a matching solution,
        # but it is an important near-miss to inspect, not a result to silently erase.
        if not constraints_match(problem, text):
            constraint_mismatch_count += 1
            constraint_near_misses.append((rel, {
                "title": p.title[:140],
                "url": p.url,
                "source": p.source,
                "snippet": (p.text or p.title)[:260],
                "missing_constraints": missing_constraints(problem, text),
                "relevance": round(rel, 2),
                "candidate_type": "existing_project" if p.source == "github_repo" else "related_product_or_discussion",
            }))
            continue
        if p.source == "github_repo":
            projects.append(_project(p))
        elif p.source in ("scholar", "arxiv"):
            papers.append(_compact(p, rel, text))
        elif p.source == "petitions":
            actions.append(_compact(p, rel, text))
        elif SOLUTION_RE.search(text):
            discussion.append(_compact(p, rel, text))

    projects.sort(key=lambda x: x["stars"], reverse=True)
    papers.sort(key=lambda x: x["score"], reverse=True)
    actions.sort(key=lambda x: x["score"], reverse=True)
    discussion.sort(key=lambda x: x["score"], reverse=True)
    sources_ok = sum(1 for s in status.values() if s.get("state") in ("ok", "partial"))
    assessment = assess(projects, papers, actions, lens, discussion, len(raw), sources_ok)
    constraint_near_misses.sort(key=lambda item: item[0], reverse=True)
    if not (projects or papers or actions or discussion) and constraint_mismatch_count and assessment["hint"] in {
        "no_clear_solution_found", "inconclusive_search_too_thin"
    }:
        assessment["hint"] = "inconclusive_constraints_not_matched"
        assessment["reasons"] = [
            f"{constraint_mismatch_count} related candidate(s) matched the subject but did not demonstrate every explicit requirement."
        ]
        assessment["caveat"] += (
            " Relevant candidates were found but did not demonstrate all requested constraints; inspect the near-misses and "
            "verify each candidate's actual capabilities before concluding the space is unsolved."
        )
    return {
        "problem": problem,
        "lens": lens,
        "searched_as": variants,
        "solution_search_queries": solution_queries,
        "required_constraints": missing_constraints(problem, ""),
        "constraint_candidates_excluded": constraint_mismatch_count,
        "constraint_near_misses": [item for _, item in constraint_near_misses[:8]],
        "coverage": status,
        "assessment": assessment,
        "existing_projects": projects[:8],
        "products_and_discussion": discussion[:8],
        "papers": papers[:6],
        "public_actions": actions[:5],
        "gap_guide": GAP_ANGLES,
        "llm_web_search_suggestions": (
            [f"{solution_queries[0]} buy price", f"{solution_queries[0]} open source",
             f"best {solution_queries[0]} alternatives", f"{solution_queries[0]} reviews complaints"]
            if lens in ("hardware", "software", "any") else web_suggestions(solution_queries[0] if solution_queries else variants[0], lens)
        ),
        "web_search_note": "If you have a web search tool, run these: this tool cannot see shops, review sites or most news.",
        "next": "Call validate_problem to check demand, then talk to 5 real people about the gap you found.",
    }
