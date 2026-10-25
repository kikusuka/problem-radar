"""Pain-phrase queries, signal detection, relevance."""
from __future__ import annotations

import math
import re

from .signal_quality import signal_profile

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
    """Require multiple generic cues or one explicit multi-word pain phrase."""
    return sum(signals(text).values()) >= 2 or signal_profile(text)["explicit_pain"]


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
    """Short, ordered queries that preserve explicit constraints and platform names.

    Do not choose only the longest words: that can drop critical terms such as
    "offline", "low-end" or "Android" from a long problem statement.
    """
    raw = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", problem.lower())
    acronyms = {w.lower() for w in re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", problem)}
    preserve_patterns = (
        r"\boffline\b|\bno[- ]internet\b|\bwithout (?:an? )?internet\b|\bno network\b|\bwithout (?:a )?network\b|\bair[- ]gapped\b|\bon[- ]device\b|\bon device\b",
        r"\blow[- ]end\b|\blow[- ]ram\b|\blow[- ]memory\b|\blow[- ]resource\b|\blow[- ]cost\b|\blow[- ]spec\b"
        r"|\blimited (?:ram|memory|resources?)\b|\bentry[- ]level\b|\bmemory[- ]constrained\b|\baffordable\b|\bprivacy[- ]first\b",
        r"\bandroid\b|\bios\b|\biphone\b|\bipad\b|\bwindows\b|\blinux\b|\bmacos\b|\bchromeos\b",
        r"\bopen[- ]source\b|\bno[- ]cost\b|\bfree\b|\bprivate\b|\bprivacy\b|\blocal (?:ai|model|llm|inference|execution|processing)\b|\bruns? locally\b|\bfully local\b",
    )
    required = set()
    for pattern in preserve_patterns:
        for match in re.finditer(pattern, problem, re.I):
            required.update(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", match.group(0).lower()))

    words = []
    for word in raw:
        if word in words or word in STOP_WORDS:
            continue
        if len(word) <= 2 and word not in acronyms and word not in required:
            continue
        if word in GENERIC and word not in required:
            continue
        words.append(word)
    if not words:
        return [problem.strip()]

    # Keep all explicitly stated constraints, then fill with terms in their original
    # order. This is deterministic, cheap, and does not need an external model.
    required_ordered = [w for w in words if w in required]
    primary = list(required_ordered)
    for word in words:
        if word not in primary and len(primary) < max(7, len(required_ordered)):
            primary.append(word)
    primary = [w for w in words if w in set(primary)]
    if len(primary) > 10:
        required_set = set(required_ordered)
        optional = [w for w in primary if w not in required_set]
        primary = [w for w in primary if w in required_set] + optional[: max(0, 10 - len(required_set))]
        primary = [w for w in words if w in set(primary)]

    out = [" ".join(primary)]
    if len(words) > 2:
        # A narrower alternative still carries every explicit constraint.
        extras = sorted(
            (w for w in words if w not in required),
            key=lambda w: (-len(w), words.index(w)),
        )[:2]
        secondary_set = set(required_ordered + extras)
        secondary = [w for w in words if w in secondary_set]
        q = " ".join(secondary)
        if q and q not in out:
            out.append(q)
    return out


# Hard constraints are extracted only when the user explicitly states them.
# The document-side patterns allow common equivalents, rather than requiring the
# exact same wording. This is intentionally conservative on the small free tier.
_CONSTRAINT_GROUPS = (
    (
        "offline operation",
        re.compile(r"\boffline\b|\bno[- ]internet\b|\bwithout (?:an? )?internet\b|\bno network\b|\bwithout (?:a )?network\b|\bair[- ]gapped\b", re.I),
        re.compile(r"\boffline\b|\bwithout (?:an? )?internet\b|\bno[- ]internet\b|\bno network\b|\bwithout (?:a )?network\b|\bair[- ]gapped\b|\bworks? without (?:an? )?internet\b", re.I),
    ),
    (
        "on-device/local execution",
        re.compile(r"\bon[- ]device\b|\b(?:local (?:ai|model|llm|inference|execution|processing)|runs? locally|fully local)\b", re.I),
        re.compile(r"\bon[- ]device\b|\bon device\b|\bfully local\b|\blocal (?:ai|model|llm|inference)\b|\bruns? locally\b|\bair[- ]gapped\b", re.I),
    ),
    (
        "low-resource hardware",
        re.compile(r"\blow[- ]end\b|\blow[- ]ram\b|\blow[- ]memory\b|\blow[- ]resource\b|\blow[- ]spec\b|\blimited (?:ram|memory|resources?)\b|\bentry[- ]level\b|\bmemory[- ]constrained\b", re.I),
        re.compile(r"\blow[- ]end\b|\blow[- ]ram\b|\blow[- ]memory\b|\blow[- ]resource\b|\blow[- ]spec\b|\blimited (?:ram|memory|resources?)\b|\bentry[- ]level\b|\bmemory[- ]constrained\b|\bolder (?:phones?|devices?)\b|\bold (?:phones?|devices?)\b|\bsmall (?:phones?|devices?)\b|\bbudget phones?\b|\b[1248] ?gb ram\b|\b2 ?gb memory\b", re.I),
    ),
    (
        "affordability",
        re.compile(r"\blow[- ]cost\b|\baffordable\b|\bcheap\b|\bbudget[- ]friendly\b|\bno[- ]cost\b|\bfree\b", re.I),
        re.compile(r"\blow[- ]cost\b|\baffordable\b|\bcheap\b|\bbudget[- ]friendly\b|\bno[- ]cost\b|\bfree\b|\bunder \$\s?\d+\b|\bcosts? (?:less|under)\b|\bfree tier\b|\bfree to use\b", re.I),
    ),
    (
        "Android platform",
        re.compile(r"\bandroid\b", re.I),
        re.compile(r"\bandroid\b|\bapk\b|\bgoogle play\b|\bandroid app\b|\bplay store\b", re.I),
    ),
    (
        "iOS platform",
        re.compile(r"\bios\b|\biphone\b|\bipad\b", re.I),
        re.compile(r"\bios\b|\biphone\b|\bipad\b|\bapple app store\b|\bipados\b", re.I),
    ),
)

_CONSTRAINT_DENIALS = {
    "offline operation": re.compile(
        r"\b(?:online[- ]only|cloud[- ]only)\b|"
        r"\b(?:requires?|needs?)\s+(?:an?\s+)?(?:internet|network|connection)\b|"
        r"\b(?:not|never|isn't|is not|doesn't run|does not run|cannot run|can't run|won't work|doesn't work)\b.{0,30}\boffline\b",
        re.I,
    ),
    "on-device/local execution": re.compile(
        r"\b(?:cloud[- ]based only|remote[- ]only|server[- ]only)\b|"
        r"\b(?:not|isn't|is not|doesn't run|does not run|cannot run|can't run|won't work)\b.{0,35}\b(?:on[- ]device|locally|local(?:\s+(?:ai|model|llm|inference|execution|processing))?)\b",
        re.I,
    ),
    "low-resource hardware": re.compile(
        r"\b(?:not suitable|not designed|doesn't run|does not run|won't run|cannot run|can't run)\b.{0,40}\b(?:low[- ]end|low[- ]ram|low[- ]memory|entry[- ]level|budget phones?)\b|"
        r"\b(?:flagship|high[- ]end)\b.{0,20}\b(?:only|required|minimum)\b|"
        r"\b(?:requires?|needs?)\s+(?:at least\s+)?(?:8|12|16)\s?gb\s+(?:of\s+)?(?:ram|memory)\b",
        re.I,
    ),
    "affordability": re.compile(
        r"\b(?:not|isn't|is not|never)\s+(?:free|cheap|affordable)\b|"
        r"\btoo expensive\b|\bnot affordable\b|\bpaid only\b|\bsubscription required\b",
        re.I,
    ),
    "Android platform": re.compile(
        r"\b(?:not supported|unsupported|not available|unavailable|doesn't run|does not run|not for)\b.{0,25}\bandroid\b|"
        r"\bandroid\b.{0,15}\b(?:unsupported|not supported)\b",
        re.I,
    ),
    "iOS platform": re.compile(
        r"\b(?:not supported|unsupported|not available|unavailable|doesn't run|does not run|not for)\b.{0,25}\b(?:ios|iphone|ipad)\b|"
        r"\b(?:ios|iphone|ipad)\b.{0,15}\b(?:unsupported|not supported)\b",
        re.I,
    ),
}


def missing_constraints(query: str, text: str) -> list[str]:
    """Return explicit user constraints not evidenced by the candidate text."""
    missing = []
    candidate = text or ""
    for label, query_re, text_re in _CONSTRAINT_GROUPS:
        if not query_re.search(query or ""):
            continue
        denial = _CONSTRAINT_DENIALS.get(label)
        if not text_re.search(candidate) or (denial and denial.search(candidate)):
            missing.append(label)
    return missing


def constraints_match(query: str, text: str) -> bool:
    """True when a candidate preserves each hard constraint stated in the query."""
    return not missing_constraints(query, text)

def _has_word(word: str, text: str, loose: bool = False) -> bool:
    """Match at the start of a word only. Short words (under 5 letters) must match whole words, so 'aid' is not
    found in 'said' and 'grip' is not found in 'gripping'. Longer words match their 5-letter stem ('invoices' ~ 'invoice')."""
    w = word.lower()
    if len(w) < 5:
        return re.search(r"\b" + re.escape(w) + r"s?\b", text, re.I) is not None
    stem = w[:5] if loose else w[:min(7, max(5, len(w) - 2))]  # 'assistive' -> 'assisti', so it does not match 'assistant'
    return re.search(r"\b" + re.escape(stem), text, re.I) is not None


def _near(words: list[str], text: str, window: int = 8) -> bool:
    """True when the words appear close together, like a phrase. 'old age home' must not match 'moved back home ... age 34 ... old'."""
    tokens = re.findall(r"[a-z0-9']+", text.lower())

    def positions(w: str) -> list[int]:
        w = w.lower()
        if len(w) < 5:
            return [i for i, t in enumerate(tokens) if t == w or t == w + "s"]
        stem = w[:min(7, max(5, len(w) - 2))]
        return [i for i, t in enumerate(tokens) if t.startswith(stem)]

    pos = [positions(w) for w in words]
    if any(not ps for ps in pos):
        return False
    return any(all(any(abs(q - a) <= window for q in ps) for ps in pos[1:]) for a in pos[0])


def mentions(term: str, text: str) -> int:
    """How many times the topic's main word appears. One passing mention does not make a post about the topic."""
    words = content_words(term)
    if not words:
        return 0
    w = max(words, key=len)
    stem = w[:min(7, max(5, len(w) - 2))] if len(w) >= 5 else w
    tokens = re.findall(r"[a-z0-9']+", text.lower())
    return sum(1 for t in tokens if (t.startswith(stem) if len(w) >= 5 else t in (w, w + "s")))


def is_focused(terms: list[str], title: str, text: str) -> bool:
    """The post is ABOUT the topic: it is in the title, in the opening lines, or comes up more than once."""
    return any(is_relevant(t, title) or is_relevant(t, text[:350]) or mentions(t, text) >= 2 for t in terms)


def relevance(niche: str, text: str, loose: bool = False) -> float:
    """Share of the niche's content words found in the text (prefix match so 'invoices' matches 'invoice')."""
    words = content_words(niche)
    if not words:
        return 0.0
    frac = sum(1 for w in words if _has_word(w, text, loose)) / len(words)
    if not loose and frac >= 1.0 and 2 <= len(words) <= 3 and not _near(words, text):
        return 0.5  # every word is present but scattered across the text, so it is not about this topic
    return frac


def is_relevant(niche: str, text: str) -> bool:
    """Short topics need every word; longer ones need about 60%."""
    n = len(content_words(niche))
    if n == 0:
        return False
    need = 1.0 if n <= 3 else 0.6
    return relevance(niche, text) >= need - 1e-9
