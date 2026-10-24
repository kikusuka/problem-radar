"""Is this problem already solved? Looks across existing projects, products, papers and public actions.

Most "does it exist?" checks only look at software repos. A problem can also be solved by a product on a shelf,
a paper that already answers the question, or a rule that already exists, so we look at all of them and say what
each source can and cannot show. The verdict is a hint; the real value is the gap analysis.
"""
from __future__ import annotations

import re
import time

from . import sources as S
from .pain import relevance
from .research import Job, _body, _compact, _dedupe, run_jobs

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


def assess(projects: list[dict], papers: list[dict], actions: list[dict], lens: str) -> dict:
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
    if not reasons:
        reasons.append("no strong existing project, paper or public action found in these sources")

    if strong or (lens == "research" and len(cited) >= 3):
        hint = "well_served_for_the_general_case"
    elif some or cited or won or projects or papers or actions:
        hint = "partially_solved"
    else:
        hint = "no_clear_solution_found"
    return {
        "hint": hint,
        "reasons": reasons,
        "is_a_hint_only": True,
        "caveat": ("Absence here is not proof nobody has solved it: these sources skew English and online, and your wording may "
                   "differ from theirs. Try other wording with search_pain, other languages and regions, and ask people."),
    }


def check(problem: str, lens: str = "software") -> dict:
    lens = lens if lens in ("software", "hardware", "policy", "research", "any") else "software"
    jobs = [Job("hn", f"Show HN {problem}", {}, 15), Job("hn", f"{problem} alternative", {}, 15)]
    if lens in ("software", "any"):
        jobs.append(Job("github_repo", problem, {}, 15))
    if lens in ("software", "research", "any"):
        jobs.append(Job("scholar", problem, {}, 15))
    if lens == "hardware":
        jobs += [Job("github_repo", f"{problem} hardware", {}, 10), Job("reddit", f'{problem} "I bought"', {}, 15),
                 Job("reddit", f"{problem} diy", {}, 15)]
    if lens == "policy":
        jobs += [Job("petitions", problem, {}, 15), Job("reddit", f"{problem} law OR policy OR campaign", {}, 15)]
    if lens == "research":
        jobs.append(Job("scholar", f"{problem} review OR survey", {}, 15))
    if S.enabled()["web"]["enabled"]:
        jobs += [Job("web", f"{problem} app OR tool OR product", {}, 10), Job("web", f"best {problem} alternatives", {}, 10)]
    raw, status = run_jobs(jobs)

    projects, discussion, papers, actions = [], [], [], []
    for p in _dedupe(raw):
        text = _body(p)
        rel = relevance(problem, text)
        if rel < 0.3:
            continue
        if p.source == "github_repo":
            projects.append(_project(p))
        elif p.source == "scholar":
            papers.append(_compact(p, rel, text))
        elif p.source == "petitions":
            actions.append(_compact(p, rel, text))
        elif SOLUTION_RE.search(text):
            discussion.append(_compact(p, rel, text))
    projects.sort(key=lambda x: x["stars"], reverse=True)
    papers.sort(key=lambda x: x["score"], reverse=True)
    actions.sort(key=lambda x: x["score"], reverse=True)
    discussion.sort(key=lambda x: x["score"], reverse=True)
    return {
        "problem": problem,
        "lens": lens,
        "coverage": status,
        "assessment": assess(projects, papers, actions, lens),
        "existing_projects": projects[:8],
        "products_and_discussion": discussion[:8],
        "papers": papers[:6],
        "public_actions": actions[:5],
        "gap_guide": GAP_ANGLES,
        "next": "Call validate_problem to check demand, then talk to 5 real people about the gap you found.",
    }
