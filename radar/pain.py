"""Pain-phrase queries, signal detection, relevance."""
from __future__ import annotations

import math
import re

# Phrase sets per solution lens: (quick, deep). People describe pain differently depending on what would fix it.
PHRASES_QUICK = [
    "is there a tool that",
    "tired of manually",
    "wish there was a way to",
    "i have to manually",
    "no way to automate",
    "biggest bottleneck",
]
PHRASES_DEEP = PHRASES_QUICK + [
    "waste hours every week",
    "why is there no",
    "how do you handle",
    "workaround for",
    "looking for software to",
    "spreadsheet for",
]
GENERAL_QUICK = [
    "wish there was a way to",
    "why is there no",
    "is there a better way to",
    "biggest frustration with",
    "no good way to",
    "someone should build",
]
GENERAL_DEEP = GENERAL_QUICK + [
    "i'm sick of",
    "waste so much time",
    "can't find a good",
    "nobody has solved",
    "how do people deal with",
    "there has to be a better",
]
HARDWARE_QUICK = [
    "wish there was a device",
    "can't find a product that",
    "no good product for",
    "i built my own",
    "diy solution for",
    "why doesn't anyone make",
]
HARDWARE_DEEP = HARDWARE_QUICK + [
    "too expensive for what it does",
    "keeps breaking",
    "looking for a gadget that",
    "there must be a gadget",
    "hack to fix",
]
POLICY_QUICK = [
    "there ought to be a law",
    "why isn't there a rule",
    "the city should",
    "someone should fix",
    "no one is responsible for",
    "who do i complain to",
]
POLICY_DEEP = POLICY_QUICK + [
    "needs regulation",
    "it's unfair that",
    "keeps happening and nothing is done",
    "should be illegal",
    "petition to",
]
RESEARCH_QUICK = [
    "open problem",
    "understudied",
    "little is known about",
    "future work",
    "remains unclear",
    "lack of data on",
]
RESEARCH_DEEP = RESEARCH_QUICK + [
    "no existing method",
    "limitations of current",
    "needs further research",
    "unexplored",
]
PHRASE_SETS = {
    "research": (RESEARCH_QUICK, RESEARCH_DEEP),
    "software": (PHRASES_QUICK, PHRASES_DEEP),
    "any": (GENERAL_QUICK, GENERAL_DEEP),
    "hardware": (HARDWARE_QUICK, HARDWARE_DEEP),
    "policy": (POLICY_QUICK, POLICY_DEEP),
}

# Evidence someone is paying for the problem, hacking around it, or asking for a solution.
MONEY_WORDS = re.compile(r"\b(pay|paying|paid|subscription|hire|hired|freelancer|budget|per month|/mo|\$\d+)\b", re.I)
HACK_WORDS = re.compile(
    r"\b(spreadsheet|excel|csv|script|workaround|work-around|zapier|copy[- ]?paste|macro|cron|manually|by hand|"
    r"diy|duct tape|jury[- ]?rig|hacked together|made my own|built my own)\b",
    re.I,
)
PAIN_WORDS = re.compile(
    r"\b(tired of|waste|wasting|hours|painful|annoying|frustrating|nightmare|tedious|hate|broken|unusable|"
    r"unsafe|dangerous|unaffordable|too expensive|inaccessible|stuck|ignored|unfair)\b",
    re.I,
)
INTENT_WORDS = re.compile(
    r"\b(is there (a|an|any) (way|tool|app|plugin|service|software|extension|device|product|gadget)"
    r"|how (do|can|would) (i|you|we) (automat\w*|bulk|batch|sync|export|convert|import)"
    r"|wish (there|i could|someone|they)|doesn't (support|work)|can't (export|import|sync|automate|find)|no way to|missing feature"
    r"|someone should|there ought to be|why (isn't|doesn't|can't) (there|anyone|anybody)|no good (way|option|product|solution)"
    r"|who do i (complain|report))\b",
    re.I,
)


GAP_WORDS = re.compile(
    r"\b(open problem|understudied|under-?explored|unexplored|future work|little is known|remains (unclear|unknown|open|challenging)"
    r"|lack of|limited (data|research|evidence)|no existing|not well understood|needs? further (research|study)|poorly understood)\b",
    re.I,
)


def gap_cues(text: str) -> int:
    """Research-gap language, for papers."""
    return len(GAP_WORDS.findall(text))


def signals(text: str) -> dict:
    return {
        "money": len(MONEY_WORDS.findall(text)),
        "hack": len(HACK_WORDS.findall(text)),
        "pain": len(PAIN_WORDS.findall(text)),
        "intent": len(INTENT_WORDS.findall(text)),
    }


def looks_like_pain(text: str) -> bool:
    """At least two cues, so one stray word like 'hours' isn't enough."""
    return sum(signals(text).values()) >= 2


def heat(text: str, score: int, comments: int) -> float:
    s = signals(text)
    return s["pain"] + s["hack"] + s["intent"] + 2 * s["money"] + math.log1p(max(score, 0)) + 0.5 * math.log1p(max(comments, 0))


DEV_HINTS = {
    "docker", "devops", "kubernetes", "python", "javascript", "typescript", "react", "api", "sdk", "github", "git",
    "llm", "ai", "developer", "developers", "software", "code", "coding", "programming", "cloud", "aws", "database",
    "backend", "frontend", "cli", "terraform", "linux", "rust", "golang", "java",
}


def is_dev_niche(niche: str) -> bool:
    return any(w in DEV_HINTS for w in re.findall(r"[a-z]+", niche.lower()))


def relevance(niche: str, text: str) -> float:
    """Share of niche words found in the text (prefix match so 'invoices' matches 'invoice')."""
    words = [w for w in re.findall(r"[a-z0-9]+", niche.lower()) if len(w) > 2]
    if not words:
        return 1.0
    low = text.lower()
    return sum(1 for w in words if w[:5] in low) / len(words)


def is_relevant(niche: str, text: str) -> bool:
    words = [w for w in re.findall(r"[a-z0-9]+", niche.lower()) if len(w) > 2]
    if not words:
        return True
    return relevance(niche, text) >= max(1, (len(words) + 1) // 2) / len(words)
