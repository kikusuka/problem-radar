"""A deterministic 0-10 pain score from what people wrote, so ranking is the same on every run.

It rewards behaviour (workarounds, money or compliance at stake, repeated pain, separate platforms agreeing) and not volume or
loudness. It is a clue for ranking, not a measure of severity: the host model still judges the posts."""
from __future__ import annotations

import re

WORKAROUND = re.compile(r"\b(?:excel|spreadsheet|csv|manual(?:ly)?|copy[- ]?paste|cron|script|workaround|by hand|whatsapp group|paper forms?|hours? (?:a|per|every) (?:day|week|month))\b", re.I)
STAKES = re.compile(r"\b(?:fine[sd]?|penalt(?:y|ies)|audit|compliance|lost (?:revenue|money|income|deposit)|churn|corrupt\w*|downtime|overcharg\w+|refund\w*|lawsuit|sue[d]?|small claims|unsafe|injur\w+)\b|[$₹£€]\s?\d", re.I)
RECUR = re.compile(r"\b(?:every (?:day|week|month|shift|semester|time)|daily|weekly|constantly|always|each (?:day|week|month|semester))\b", re.I)
NOISE = re.compile(r"\b(?:ugly|dark mode|logo|font|color scheme)\b", re.I)


def score(texts: list[str], platforms: int = 1) -> dict:
    """texts: the posts in one group. platforms: number of distinct source types among them."""
    blob = " ".join(texts)
    parts = {
        "workaround": 3 if WORKAROUND.search(blob) else 0,
        "stakes": 3 if STAKES.search(blob) else 0,
        "recurrence": 2 if RECUR.search(blob) else 0,
        "cross_source": 2 if platforms >= 2 else 0,
        "noise": -3 if (NOISE.search(blob) or all(len(t) < 80 for t in texts)) else 0,
    }
    return {"pain_score": max(0, min(10, sum(parts.values()))), "pain_parts": parts,
            "pain_note": "Counts signals in the post text (workaround, money or compliance at stake, recurrence, separate platforms). A ranking clue, not severity."}


RUBRIC = """# Student viability rubric (0-2 per row, 10 total)

| Criterion | 0 | 1 | 2 |
|---|---|---|---|
| Workaround pain | mild annoyance, people do nothing | clear frustration, occasional manual fix | active, costly workaround (spreadsheets, scripts, paid help) |
| Frequency | rare or one-off | monthly or per project | daily or weekly |
| User reachability | needs enterprise sales or approvals | reachable in niche online communities | reachable locally, on campus or through open repositories |
| Existing tool gap | solved well by free, popular tools | tools exist but are costly or bloated | existing tools fail a clear constraint (offline, local format, language, privacy) |
| Build scope | custom hardware, wet lab or over 3 months | 4-8 weeks | working MVP in 1-3 weeks with public data or APIs |

8-10: build now (talk to 3-5 sufferers this week). 5-7: narrow the wedge to one constraint first. 0-4: skip.
Score from evidence you can cite; a row you cannot support gets 0. The scores are your judgment, not a server measurement.
"""
