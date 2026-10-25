"""Transparent pain-signal annotations adapted from ScopeScrape's MIT-licensed detector.

Upstream: https://github.com/cvasan2sh/scopescrape_tool
See THIRD_PARTY_NOTICES.md for copyright and licence text.

This module is deliberately dependency-free. Its phrases are cues for ranking and
inspection, not proof that a complaint is genuine or representative.
"""
from __future__ import annotations

import re


# Phrase taxonomy adapted from ScopeScrape's SignalDetector.
# Categories describe the kind of evidence, not whether a claim is true.
SIGNAL_PHRASES: dict[str, tuple[tuple[str, str], ...]] = {
    "pain_point": (
        ("frustrated with", "emotion"),
        ("frustrating", "emotion"),
        ("i'm struggling", "emotion"),
        ("i struggle with", "emotion"),
        ("struggling to", "emotion"),
        ("pain point", "emotion"),
        ("dealbreaker", "emotion"),
        ("deal breaker", "emotion"),
        ("can't stand", "emotion"),
        ("driving me crazy", "emotion"),
        ("pulling my hair out", "emotion"),
        ("at my wit's end", "emotion"),
        ("broken", "bug"),
        ("keeps crashing", "bug"),
        ("crashes constantly", "bug"),
        ("doesn't work", "bug"),
        ("stopped working", "bug"),
        ("not working", "bug"),
        ("buggy", "bug"),
        ("unreliable", "bug"),
        ("constantly breaks", "bug"),
        ("waste of time", "workflow"),
        ("wasting my time", "workflow"),
        ("too slow", "workflow"),
        ("takes forever", "workflow"),
        ("too complicated", "workflow"),
        ("overly complex", "workflow"),
        ("clunky", "workflow"),
        ("bloated", "workflow"),
        ("unusable", "workflow"),
    ),
    "emotional": (
        ("i hate", "emotion"),
        ("i despise", "emotion"),
        ("terrible", "emotion"),
        ("awful", "emotion"),
        ("worst", "emotion"),
        ("horrible", "emotion"),
        ("nightmare", "emotion"),
        ("regret", "emotion"),
        ("i wish", "feature_request"),
        ("if only", "feature_request"),
        ("would be nice if", "feature_request"),
        ("why can't", "feature_request"),
        ("why doesn't", "feature_request"),
        ("should be able to", "feature_request"),
        ("needs to support", "feature_request"),
        ("missing feature", "feature_request"),
        ("desperately need", "feature_request"),
        ("pray", "emotion"),
    ),
    "comparison": (
        ("vs", "tool_eval"),
        ("versus", "tool_eval"),
        ("compared to", "tool_eval"),
        ("better than", "tool_eval"),
        ("worse than", "tool_eval"),
        ("alternative to", "tool_eval"),
        ("alternatives to", "tool_eval"),
        ("replacement for", "tool_eval"),
        ("instead of", "tool_eval"),
        ("switched from", "migration"),
        ("switching from", "migration"),
        ("moved from", "migration"),
        ("moving from", "migration"),
        ("migrated from", "migration"),
        ("migrating from", "migration"),
        ("ditched", "migration"),
        ("dropped", "migration"),
    ),
    "ask": (
        ("how to", "help_seeking"),
        ("how do i", "help_seeking"),
        ("how do you", "help_seeking"),
        ("anyone know", "help_seeking"),
        ("does anyone know", "help_seeking"),
        ("any recommendations", "help_seeking"),
        ("can someone recommend", "help_seeking"),
        ("what do you use for", "help_seeking"),
        ("what tool", "help_seeking"),
        ("is there a way", "help_seeking"),
        ("is there a tool", "help_seeking"),
        ("looking for", "help_seeking"),
        ("looking for a tool", "help_seeking"),
        ("need a tool", "help_seeking"),
        ("anyone recommend", "help_seeking"),
        ("suggestions for", "help_seeking"),
        ("best way to", "help_seeking"),
        ("any good", "help_seeking"),
    ),
}

TIER_WEIGHTS = {"pain_point": 1.0, "emotional": 0.8, "comparison": 0.6, "ask": 0.4}

_COMPILED = {
    tier: [
        (re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE), phrase, category)
        for phrase, category in phrases
    ]
    for tier, phrases in SIGNAL_PHRASES.items()
}

# Detect product promotion without mistaking ordinary first-person complaints for ads.
# Some launch announcements avoid "I/we built" and use an announcement + download CTA.
_PROMO_TRIGGER = re.compile(
    r"\b(?:i|we)\s+(?:built|made|created|designed|developed|founded|launched)\b",
    re.IGNORECASE,
)
_PROMO_ANNOUNCEMENT = re.compile(
    r"\b(?:excited to announce|huge news|big milestone|pleased to announce|"
    r"officially approved|now live|just launched|new release|available to download|"
    r"live on (?:the )?(?:apple )?app store)\b",
    re.IGNORECASE,
)
_PROMO_CTA = re.compile(
    r"\b(?:check it out|happy to share|beta|launching|sign up|try it(?: out)?|"
    r"give it a try|feedback welcome|open beta|available now|join the waitlist|"
    r"download(?: it| directly)?(?: now)?|get it on|app store|google play)\b",
    re.IGNORECASE,
)


# Evidence labels are lightweight, inspectable heuristics—not truth labels.
_FAILURE_CONTEXT = re.compile(
    # Strong failure evidence, not generic mentions of "bug", "error", or "crash"
    # embedded in an educational post or a description of a product feature.
    r"\b(?:keeps? crashing|crash(?:es|ed|ing)?\s+(?:when|after|on|during|because|with|at)|"
    r"freez(?:e|es|ing|en)?\s+(?:when|after|on|during|because|with|at)|"
    r"hangs?\s+(?:when|after|on|during|because|with|at)|hung\s+(?:when|after|on|during)|"
    r"out[-\s]?of[-\s]?(?:memory|ram)|oom|memory leak|not enough ram|"
    r"failed to allocate|fatal exception|stack trace|steps to reproduce|"
    r"(?:my|our|this|the app|the application|the model|the runtime|the device|the process|it)\b.{0,45}"
    r"\b(?:crashes|crashed|crashing|freezes|freezing|hangs|hung|fails to load|doesn't work|does not work)|"
    r"(?:crash|freez|hang|fail(?:ure)? to load)\w*\s+(?:bug|issue|report|problem))\b",
    re.IGNORECASE,
)
_TUTORIAL_TITLE = re.compile(
    r"^\s*(?:everything i learned|what i learned|lessons learned|guide to\b|"
    r"a practical guide\b|tutorial\b|walkthrough\b|deep dive into\b|"
    r"getting started with\b|how to (?:build|run|deploy|use|integrate|implement|create|install)\b|"
    r"building .{1,100}\binto\b|from scratch:\s)",
    re.IGNORECASE,
)
_WORKAROUND_CONTEXT = re.compile(
    r"\b(?:workaround|work-around|work around|hack(?:ed)? together|manual(?:ly)?|"
    r"copy[- ]?paste|spreadsheet|script to|built my own)\b",
    re.IGNORECASE,
)
_HELP_REQUEST = re.compile(
    r"\b(?:how do i|how can i|anyone know|does anyone know|any recommendations|"
    r"what do you use|looking for|is there a way|is there a tool|can someone recommend)\b",
    re.IGNORECASE,
)
_PRODUCT_COMPARISON = re.compile(
    r"\b(?:versus|\bvs\.?\b|alternative to|alternatives to|replacement for|"
    r"compared with|compared to|better than|worse than)\b",
    re.IGNORECASE,
)
_SOLUTION_TITLE = re.compile(
    r"^\s*(?:show hn:\s*)?[a-z][a-z0-9_.+-]{1,35}\s*(?:[-—:|]\s+).{0,160}"
    r"\b(?:library|sdk|framework|toolkit|app|package|server|client|extension|plugin|repo|project)\b",
    re.IGNORECASE,
)
_SOLUTION_INTRO = re.compile(
    r"\b(?:introducing|meet)\s+[a-z][a-z0-9_.+-]{2,}\b|"
    r"\bmy new (?:app|tool|library|sdk|framework|package|assistant|model)\b|"
    r"\b(?:open[- ]source )?(?:library|sdk|framework|toolkit|package) for\b",
    re.IGNORECASE,
)

def signal_profile(text: str, max_matches: int = 8) -> dict:
    """Return transparent pain-signal annotations and a coarse evidence class."""
    text = text or ""
    promotional = bool(
        (_PROMO_TRIGGER.search(text) and _PROMO_CTA.search(text))
        or (_PROMO_ANNOUNCEMENT.search(text) and _PROMO_CTA.search(text))
    )
    found: list[tuple[int, str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    for tier, patterns in _COMPILED.items():
        for pattern, phrase, category in patterns:
            match = pattern.search(text)
            key = (tier, phrase)
            if match and key not in seen:
                seen.add(key)
                found.append((match.start(), tier, phrase, category))

    found.sort(key=lambda item: (-TIER_WEIGHTS[item[1]], item[0], item[2]))
    counts = {tier: 0 for tier in SIGNAL_PHRASES}
    for _, tier, _, _ in found:
        counts[tier] += 1

    raw_score = sum(TIER_WEIGHTS[tier] for _, tier, _, _ in found)
    confidence = 0.5 if promotional else 1.0
    matches = [
        {
            "phrase": phrase,
            "tier": tier,
            "category": category,
            "confidence": confidence,
        }
        for _, tier, phrase, category in found[:max(0, max_matches)]
    ]

    # A generic single word such as "broken" is not enough to pass the complaint
    # gate. This flag remains intentionally stricter than the evidence class.
    explicit_pain = any(
        tier == "pain_point" and len(phrase.split()) >= 2
        for _, tier, phrase, _ in found
    )

    if promotional:
        evidence_kind = "product_announcement"
    # Artifact type comes before technical vocabulary: tutorials often mention bugs,
    # crashes, memory errors, or lessons learned without reporting a user's complaint.
    elif _TUTORIAL_TITLE.search(text):
        evidence_kind = "technical_tutorial"
    # A launch/demo-style title is stronger evidence of a solution showcase than
    # failure vocabulary embedded later in its description (e.g. "fallback when it
    # wedges"). Classify the artifact being presented before its feature/problem terms.
    elif _SOLUTION_TITLE.search(text) or _SOLUTION_INTRO.search(text):
        evidence_kind = "solution_showcase"
    elif _FAILURE_CONTEXT.search(text):
        evidence_kind = "technical_failure_report"
    elif explicit_pain:
        evidence_kind = "reported_complaint"
    elif _WORKAROUND_CONTEXT.search(text):
        evidence_kind = "workaround_or_manual_process"
    elif _HELP_REQUEST.search(text):
        evidence_kind = "help_request"
    elif _PRODUCT_COMPARISON.search(text):
        evidence_kind = "product_comparison"
    else:
        evidence_kind = "general_discussion"

    return {
        "counts": counts,
        "matches": matches,
        "weighted_score": min(3.0, raw_score),
        "promotional": promotional,
        "explicit_pain": explicit_pain,
        "evidence_kind": evidence_kind,
    }
