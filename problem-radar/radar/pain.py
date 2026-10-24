"""Pain-phrase queries and signal detection."""
from __future__ import annotations

import re

PAIN_PHRASES = [
    "is there a tool that",
    "tired of manually",
    "waste hours every week",
    "wish there was a way to",
    "no way to automate",
    "i have to manually",
    "why is there no",
    "biggest bottleneck",
]

# Evidence someone is paying for the problem or hacking around it.
MONEY_WORDS = re.compile(r"\b(pay|paying|paid|subscription|hire|hired|freelancer|budget|per month|/mo|\$\d+)\b", re.I)
HACK_WORDS = re.compile(
    r"\b(spreadsheet|excel|csv|script|workaround|work-around|zapier|copy[- ]?paste|macro|cron|manually|by hand)\b", re.I
)
PAIN_WORDS = re.compile(
    r"\b(tired of|waste|wasting|hours|painful|annoying|frustrating|nightmare|tedious|hate|broken|unusable)\b", re.I
)


def build_queries(niche: str) -> list[str]:
    """One query per pain phrase, anchored on the niche."""
    return [f'{niche} "{p}"' for p in PAIN_PHRASES]


def signals(text: str) -> dict:
    return {
        "money": len(MONEY_WORDS.findall(text)),
        "hack": len(HACK_WORDS.findall(text)),
        "pain": len(PAIN_WORDS.findall(text)),
    }


def looks_like_pain(text: str) -> bool:
    s = signals(text)
    return (s["pain"] + s["hack"] + s["money"]) > 0
