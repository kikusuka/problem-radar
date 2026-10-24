"""Hunt planner and domain explorer: for people who don't yet know where to look.

A good problem is not just a painful one. It is painful, evidenced, solvable BY YOU, under-served, and right for your goal.
So the hunt starts from the person (goal, skills, time, budget, interests) and only then searches.
"""
from __future__ import annotations

import re

from .research import FIT_RUBRIC, build_guide

DOMAINS = [
    {"domain": "health and aging", "niches": ["medication management", "elder care coordination", "caregiver burnout", "hospital discharge", "fall prevention"], "fits": ["software", "hardware", "policy"]},
    {"domain": "accessibility", "niches": ["hand mobility aids", "hearing aid cost", "wheelchair route planning", "tactile navigation for blind users", "screen reader problems", "captioning", "sensory overload", "communication boards"], "fits": ["software", "hardware", "policy"]},
    {"domain": "education", "niches": ["teacher grading workload", "student mental health", "school lunch", "homework tracking", "classroom tech"], "fits": ["software", "policy"]},
    {"domain": "small business", "niches": ["invoicing", "inventory tracking", "appointment scheduling", "customer follow-up", "bookkeeping"], "fits": ["software"]},
    {"domain": "housing and renting", "niches": ["tenant repairs", "landlord communication", "rent increases", "home energy bills", "mold and damp"], "fits": ["software", "hardware", "policy"]},
    {"domain": "transport and commuting", "niches": ["bus reliability", "bike safety", "parking", "EV charging", "school run logistics"], "fits": ["software", "hardware", "policy"]},
    {"domain": "food and farming", "niches": ["food waste", "small farm equipment", "irrigation", "grocery prices", "community gardens"], "fits": ["software", "hardware", "policy"]},
    {"domain": "energy and climate", "niches": ["home energy use", "heat pumps", "recycling", "flood risk", "solar for renters"], "fits": ["software", "hardware", "policy"]},
    {"domain": "government and civic services", "niches": ["permit delays", "benefits applications", "311 complaints", "voting access", "public records"], "fits": ["software", "policy"]},
    {"domain": "work and freelancing", "niches": ["client payments", "scope creep", "job search", "remote work", "burnout"], "fits": ["software", "policy"]},
    {"domain": "parenting and childcare", "niches": ["childcare cost", "school logistics", "screen time", "baby sleep", "children's safety"], "fits": ["software", "hardware", "policy"]},
    {"domain": "personal finance", "niches": ["budgeting", "subscription tracking", "bills", "taxes", "debt"], "fits": ["software", "policy"]},
    {"domain": "safety and public space", "niches": ["street lighting", "noise", "pedestrian crossings", "package theft", "graffiti"], "fits": ["hardware", "policy", "software"]},
    {"domain": "developer experience", "niches": ["flaky CI", "documentation", "onboarding", "API testing", "dependency updates"], "fits": ["software"]},
]

SOFTWARE_SKILLS = {"computer", "cs", "informatics", "python", "javascript", "typescript", "react", "web", "app", "coding", "programming", "software", "developer", "ml", "ai", "backend", "frontend"}
HARDWARE_SKILLS = {"arduino", "electronics", "soldering", "3d", "printing", "robotics", "raspberry", "iot", "hardware", "cad", "woodworking", "mechanical"}
RESEARCH_SKILLS = {"biology", "chemistry", "physics", "lab", "research", "statistics", "medicine", "psychology", "neuroscience", "thesis", "math", "mathematics"}
POLICY_SKILLS = {"policy", "law", "legal", "advocacy", "civic", "community", "organizing", "writing", "research", "politics", "nonprofit"}


STUDENT_DOMAINS = [
    {"domain": "student: campus life", "niches": ["study group scheduling", "campus navigation", "lost and found", "club management", "dorm problems"], "fits": ["software", "hardware", "policy"]},
    {"domain": "student: wellbeing", "niches": ["exam stress", "sleep", "loneliness", "burnout", "procrastination"], "fits": ["software", "policy", "research"]},
    {"domain": "student: study tools", "niches": ["note taking", "flashcards", "citation management", "group projects", "lecture recordings"], "fits": ["software"]},
    {"domain": "student: money", "niches": ["textbook costs", "student housing", "part-time jobs", "scholarship search", "food costs"], "fits": ["software", "policy"]},
    {"domain": "student: campus sustainability", "niches": ["campus food waste", "energy use in dorms", "recycling", "bike parking", "water use"], "fits": ["software", "hardware", "policy", "research"]},
    {"domain": "student: accessibility on campus", "niches": ["accessible routes", "assistive tech cost", "captioning lectures", "learning disabilities", "low-vision tools"], "fits": ["software", "hardware", "policy"]},
    {"domain": "student: research workflow", "niches": ["literature review", "reproducibility", "data cleaning", "lab inventory", "survey tools"], "fits": ["software", "research"]},
    {"domain": "student: access to opportunities", "niches": ["internship search", "scholarship deadlines", "mentor matching", "first-generation students"], "fits": ["software", "policy", "research"]},
]
LEVELS = {
    "high school": "Prefer problems you can see in your own school or community. Get adult sign-off for experiments, and be careful with data about other students.",
    "undergraduate": "Prefer one narrow, real user and a result you can measure. Check your course or capstone rules before you commit.",
    "masters": "Novelty starts to matter. Read 5 recent papers or products first, and pick a gap they themselves admit.",
    "phd": "Novelty and contribution decide. Anchor on a gap stated in recent papers and a method you can defend.",
}
STUDENT_RUBRIC = {
    "feasible for you (30)": "Fits your time, skills, resources and mentor access, with a clear first milestone.",
    "learning and portfolio value (20)": "You learn something real and end with something you can show.",
    "pain and evidence (25)": "Real people have it, shown by independent voices or official counts.",
    "access to users or data (15)": "You can reach real users or get real data without special permissions.",
    "novelty or gap (10)": "Not already solved well, or you have a specific angle the leader misses.",
}


def explore_domains(interest: str = "") -> dict:
    """Seed ideas for people who don't know where to start. Filter by a word like 'health' or 'city'."""
    words = [w for w in re.findall(r"[a-z]+", interest.lower()) if len(w) > 2]
    pool = DOMAINS + STUDENT_DOMAINS
    picked = [d for d in pool if not words or any(w[:5] in (d["domain"] + " " + " ".join(d["niches"])).lower() for w in words)]
    return {
        "domains": picked or pool,
        "matched_your_interest": bool(picked) or not words,
        "next": "Pick 2-3 niches and call research_niche on each (set lens to match the fix you can deliver).",
    }


def _lens_from(skills: list[str], explicit: str) -> str:
    if explicit in ("software", "hardware", "policy", "research"):
        return explicit
    toks = {w for s in skills for w in re.findall(r"[a-z0-9]+", s.lower())}
    scores = {"software": len(toks & SOFTWARE_SKILLS), "hardware": len(toks & HARDWARE_SKILLS),
              "policy": len(toks & POLICY_SKILLS), "research": len(toks & RESEARCH_SKILLS)}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "any"


def plan_hunt(goal: str = "general", interests: list[str] | None = None, skills: list[str] | None = None,
              hours: str = "", budget: str = "", lens: str = "any", location: str = "") -> dict:
    """Turn a person's situation into a research plan. Call this first when the user is unsure what to search."""
    interests, skills = interests or [], skills or []
    chosen = _lens_from(skills, lens)
    seeds, seen = [], set()
    for i in interests or [""]:
        for d in explore_domains(i)["domains"][:3]:
            for n in d["niches"][:2]:
                if n not in seen and (chosen == "any" or chosen in d["fits"]):
                    seen.add(n)
                    seeds.append({"niche": n, "domain": d["domain"], "lens": chosen})
    seeds = seeds[:6]
    return {
        "profile": {"goal": goal, "interests": interests, "skills": skills, "hours": hours, "budget": budget,
                    "location": location},
        "lens": chosen,
        "lens_reason": "from your skills" if chosen != "any" and lens == "any" else ("as requested" if lens != "any" else "no clear skill signal; the analyst will pick the fix type per problem"),
        "seed_niches": seeds,
        "steps": [
            "1. If interests or skills are missing, ask the person two short questions before searching.",
            f"2. Call research_niche for 3 of the seed niches with lens='{chosen}' and goal='{goal}'.",
            "3. Group and score the findings with the fit_rubric. The 'fit for you' score must use the profile above.",
            "4. Shortlist 3 problems. Call validate_problem on each.",
            "5. Present the top pick, one backup, and what to check with 5 real people before building.",
        ],
        "fit_rubric": FIT_RUBRIC,
        "analysis_guide": build_guide(chosen, goal),
        "location_note": ("Official civic data covers only the UK and New York City; for other places use search_pain."
                          if chosen in ("policy", "any") and location else ""),
    }


def _scope(weeks: float, goal: str) -> list[str]:
    if goal == "hackathon" or weeks <= 0.5:
        return ["One core feature and one 3-minute demo. Cut everything else.", "Use data or APIs that already exist; no time to collect your own."]
    if goal == "science_fair":
        return ["One testable hypothesis, one variable you change, one thing you measure.", "Cheap, safe materials and adult supervision where needed."]
    if weeks <= 6:
        return ["One user, one core feature, one measurable result.", "Have a working version by the halfway point; polish after."]
    if weeks <= 20:
        return ["One user group, one data source, one evaluation (a survey, a test, a metric).", "Agree scope with your instructor early; write down what is out of scope."]
    return ["Plan milestones every month and a fallback scope if the main idea stalls.", "Line up a mentor and a real user or dataset in the first month."]


def student_hunt(level: str = "undergraduate", field: str = "", goal: str = "class_project", weeks: float = 8,
                 team_size: int = 1, interests: list[str] | None = None, resources: str = "", location: str = "") -> dict:
    """A research plan for a student: what to hunt, how big, and how to judge it."""
    interests = interests or []
    lvl = level.lower().strip()
    lvl = lvl if lvl in LEVELS else ("high school" if "school" in lvl else "undergraduate")
    lens = "research" if goal in ("research",) else _lens_from([field] + interests, "any")
    seeds, seen = [], set()
    for i in interests or [field or ""]:
        for d in explore_domains(i)["domains"][:4]:
            for n in d["niches"][:3]:
                if n not in seen and (lens == "any" or lens in d["fits"]):
                    seen.add(n)
                    seeds.append({"niche": n, "domain": d["domain"]})
    seeds = seeds[:8]
    ethics = ("If your project collects data from people, get permission first (teacher, supervisor or ethics board), keep it anonymous, "
              "and take extra care with minors.")
    return {
        "profile": {"level": lvl, "field": field, "goal": goal, "weeks": weeks, "team_size": team_size,
                    "interests": interests, "resources": resources, "location": location},
        "lens": lens,
        "level_note": LEVELS[lvl],
        "scope_guardrails": _scope(weeks, goal),
        "ethics_note": ethics,
        "seed_niches": seeds,
        "steps": [
            "1. If field, time available or interests are missing, ask the student two short questions first.",
            f"2. Call research_niche for 3 seed niches with lens='{lens}' and goal='{goal if goal in ('hackathon','class_project','capstone','research','science_fair') else 'general'}'."
            + (" For a research goal use find_research_gaps." if lens == "research" else ""),
            "3. Score candidates with student_rubric. 'Feasible for you' must use the profile above.",
            "4. For the top 3, call check_if_solved, then validate_problem on the best two.",
            "5. Present one recommended project, one backup, a week-by-week outline that fits the time, and what to check with a teacher or real user before starting.",
        ],
        "student_rubric": STUDENT_RUBRIC,
        "analysis_guide": build_guide(lens, goal),
    }
