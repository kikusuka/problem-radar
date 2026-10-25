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


def signal_profile(text: str, max_matches: int = 8) -> dict:
    """Return concise, transparent phrase evidence and a capped ranking bonus."""
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

    # Only a multi-word, explicit frustration/breakage phrase can independently
    # satisfy the pain gate. Generic single words like "broken" or "worst" cannot.
    explicit_pain = any(
        tier == "pain_point" and len(phrase.split()) >= 2
        for _, tier, phrase, _ in found
    )

    return {
        "counts": counts,
        "matches": matches,
        "weighted_score": min(3.0, raw_score),
        "promotional": promotional,
        "explicit_pain": explicit_pain,
    }
