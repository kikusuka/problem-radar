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
from .pain import constraints_match, missing_constraints, query_variants, relevance, topic_anchor_gaps, topic_candidate_fit, topic_fit
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


def check(problem: str, lens: str = "software") -> dict:
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("problem must be a non-empty string")
    problem = problem.strip()
    if len(problem) > MAX_QUERY_CHARS:
        raise ValueError(f"problem must be at most {MAX_QUERY_CHARS} characters")
    lens = lens if lens in ("software", "hardware", "policy", "research", "any") else "software"
    variants = query_variants(problem)
    jobs: list[Job] = []
    for v in variants:
        jobs += [Job("hn", f"Show HN {v}", {}, 20), Job("hn", f"{v} alternative", {}, 20)]
        if lens in ("software", "any", "hardware"):
            jobs.append(Job("github_repo", v if lens != "hardware" else f"{v} open source", {}, 15))
        if lens in ("software", "research", "any", "hardware"):
            jobs.append(Job("scholar", v, {}, 15))
        if lens == "research":
            jobs.append(Job("arxiv", v, {}, 15))
        if lens == "hardware":
            jobs += [Job("reddit", f"{v} diy", {}, 15), Job("reddit", f"{v} I bought", {}, 15)]
        if lens == "policy":
            jobs += [Job("petitions", v, {}, 15), Job("reddit", f"{v} law OR policy OR campaign", {}, 15)]
    raw, status = run_jobs(jobs)

    key = variants[0]
    projects, discussion, papers, actions = [], [], [], []
    constraint_mismatch_count = 0
    constraint_near_misses: list[tuple[float, dict]] = []
    related_topic_candidates: list[tuple[float, dict]] = []
    for p in _dedupe(raw):
        text = _body(p)
        rel = max((relevance(variant, text) for variant in variants), default=0.0)
        # Strict topic matches can support the structured solution assessment. Partial
        # matches are retained separately so a project/paper isn't hidden merely
        # because its title uses a neighboring term (e.g. "LLM runner" not "assistant").
        if rel < 0.5:
            continue
        strict_topic_match = topic_fit(problem, text, p.title)
        if not strict_topic_match:
            if topic_candidate_fit(problem, text, p.title):
                candidate_kind = (
                    "existing_project_candidate" if p.source == "github_repo"
                    else "paper_candidate" if p.source in ("scholar", "arxiv")
                    else "discussion_candidate"
                )
                related_topic_candidates.append((rel, {
                    "title": p.title[:140],
                    "url": p.url,
                    "source": p.source,
                    "candidate_kind": candidate_kind,
                    "snippet": (p.text or p.title)[:260],
                    "missing_topic_anchors": topic_anchor_gaps(problem, text, p.title),
                    "missing_constraints": missing_constraints(problem, text),
                    "relevance": round(rel, 2),
                }))
            continue
        if not constraints_match(problem, text):
            constraint_mismatch_count += 1
            constraint_near_misses.append((rel, {
                "title": p.title[:140],
                "url": p.url,
                "source": p.source,
                "snippet": (p.text or p.title)[:260],
                "missing_constraints": missing_constraints(problem, text),
                "relevance": round(rel, 2),
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
    related_topic_candidates.sort(key=lambda item: item[0], reverse=True)
    if not (projects or papers or actions or discussion) and constraint_mismatch_count and assessment["hint"] == "no_clear_solution_found":
        assessment["hint"] = "inconclusive_constraints_not_matched"
        assessment["reasons"] = [f"{constraint_mismatch_count} related candidate(s) did not demonstrate all explicit constraints."]
        assessment["caveat"] += " A candidate was excluded if it did not show the requested offline, hardware/resource or platform constraint; inspect related results and broaden the search before concluding."
    elif not (projects or papers or actions or discussion) and related_topic_candidates and assessment["hint"] == "no_clear_solution_found":
        assessment["hint"] = "inconclusive_related_candidates"
        assessment["reasons"] = [
            f"{len(related_topic_candidates)} candidate(s) share important topic anchors but do not establish a full topic match. Inspect related_candidates before concluding."
        ]
        assessment["caveat"] += " Partial topic matches are shown for inspection only; they do not prove an existing solution fits the full problem or constraints."
    return {
        "problem": problem,
        "lens": lens,
        "searched_as": variants,
        "required_constraints": missing_constraints(problem, ""),
        "constraint_candidates_excluded": constraint_mismatch_count,
        "constraint_near_misses": [item for _, item in constraint_near_misses[:5]],
        "related_candidate_count": len(related_topic_candidates),
        "related_candidates": [item for _, item in related_topic_candidates[:8]],
        "coverage": status,
        "assessment": assessment,
        "existing_projects": projects[:8],
        "products_and_discussion": discussion[:8],
        "papers": papers[:6],
        "public_actions": actions[:5],
        "gap_guide": GAP_ANGLES,
        "llm_web_search_suggestions": (
            [f"{variants[0]} buy price", f"{variants[0]} open source", f"best {variants[0]} alternatives", f"{variants[0]} reviews complaints"]
            if lens in ("hardware", "software", "any") else web_suggestions(variants[0], lens)
        ),
        "web_search_note": "If you have a web search tool, run these: this tool cannot see shops, review sites or most news.",
        "next": "Call validate_problem to check demand, then talk to 5 real people about the gap you found.",
    }
