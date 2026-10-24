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
    return s["pain"] + s["hack"] + s["intent"] + 2 * min(s["money"], 4) + math.log1p(max(score, 0)) + 0.5 * math.log1p(max(comments, 0))


DEV_HINTS = {
    "docker", "devops", "kubernetes", "python", "javascript", "typescript", "react", "api", "sdk", "github", "git",
    "llm", "ai", "developer", "developers", "software", "code", "coding", "programming", "cloud", "aws", "database",
    "backend", "frontend", "cli", "terraform", "linux", "rust", "golang", "java",
}


def is_dev_niche(niche: str) -> bool:
    return any(w in DEV_HINTS for w in re.findall(r"[a-z]+", niche.lower()))


STOP_WORDS = set(
    "the and for with from into onto over under about that this these those you your our their his her its are was were "
    "been being have has had can could should would will not but all any how what why when where who which than then also "
    "one two use used using via per".split()
)
GENERIC = {"low", "cost", "people", "person", "better", "easy", "easier", "simple", "new", "good", "best", "help", "helps",
           "helping", "way", "something", "thing", "limited", "small", "large", "big", "make", "makes", "need", "needs"}

# Single-word modifiers: broad queries ("niche + word") return posts; local pain filtering then picks the real ones.
# (Exact phrases AND a niche returned almost nothing for specific topics when tested live.)
MODIFIERS = {
    "software": ["problem", "manually", "automate", "workaround", "frustrating", "tool", "wish", "slow"],
    "any": ["problem", "frustrating", "wish", "struggle", "expensive", "difficult", "annoying", "unfair"],
    "hardware": ["expensive", "diy", "broken", "wish", "alternative", "struggle", "cheap", "hack"],
    "policy": ["unfair", "dangerous", "complaint", "should", "ignored", "petition", "problem", "cost"],
    "research": ["understudied", "unclear", "challenge", "limitations", "gap", "unexplored", "lack", "future"],
}


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP_WORDS]


def query_variants(problem: str) -> list[str]:
    """Shorter keyword queries from a long problem statement (long sentences match almost nothing)."""
    words, seen = [w for w in content_words(problem) if w not in GENERIC], []
    for w in words:
        if w not in seen:
            seen.append(w)

    def top(n: int) -> str:
        keep = set(sorted(seen, key=len, reverse=True)[:n])
        return " ".join(w for w in seen if w in keep)

    out = [top(4)] if seen else []
    if len(seen) > 2:
        out.append(top(2))
    return out or [problem]


def _has_word(word: str, text: str, loose: bool = False) -> bool:
    """Match at the start of a word only. Short words (under 5 letters) must match whole words, so 'aid' is not
    found in 'said' and 'grip' is not found in 'gripping'. Longer words match their 5-letter stem ('invoices' ~ 'invoice')."""
    w = word.lower()
    if len(w) < 5:
        return re.search(r"\b" + re.escape(w) + r"s?\b", text, re.I) is not None
    stem = w[:5] if loose else w[:min(7, max(5, len(w) - 2))]  # 'assistive' -> 'assisti', so it does not match 'assistant'
    return re.search(r"\b" + re.escape(stem), text, re.I) is not None


def relevance(niche: str, text: str, loose: bool = False) -> float:
    """Share of the niche's content words found in the text (prefix match so 'invoices' matches 'invoice')."""
    words = content_words(niche)
    if not words:
        return 1.0
    return sum(1 for w in words if _has_word(w, text, loose)) / len(words)


def is_relevant(niche: str, text: str) -> bool:
    """Short topics need every word; longer ones need about 60%."""
    n = len(content_words(niche))
    if n == 0:
        return True
    need = 1.0 if n <= 3 else 0.6
    return relevance(niche, text) >= need - 1e-9
