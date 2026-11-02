"""Group posts by the SHAPE of the complaint, not by shared topic words.

Inside one topic every post shares the topic words, so word overlap cannot separate "the landlord ignores me" from
"the landlord invented charges". These families name what went wrong. They are generic (no domain or country words)
and only a hint: the host LLM still reads the posts and writes the final problem statements."""
from __future__ import annotations

import re

FAMILIES: dict[str, tuple[str, str]] = {
    "ignored": ("Nobody responds", r"ignor\w*|ghost\w*|unrespons\w*|no (?:reply|response|answer)|not (?:replying|responding|answering)|doesn'?t (?:reply|respond|answer)|won'?t (?:reply|respond|answer)|silent|radio silence"),
    "refused": ("Refuses or withholds what is owed", r"refus\w*|withh[eo]ld\w*|won'?t (?:give|pay|return|refund)|not (?:returning|paying|refunding)|keeps? (?:my|the|our)|steal\w*|stole\w*|denied|rejected"),
    "overcharged": ("Unexpected or inflated charges", r"overcharg\w*|hidden (?:fee|charge|cost)s?|extra (?:fee|charge|cost)s?|deduct\w*|charged me|surprise (?:fee|bill)|billing error|rip\w* off|price gouging|too expensive|can'?t afford|unaffordable"),
    "delayed": ("Delays and waiting", r"delay\w*|waiting (?:for|since|weeks|months)|weeks? (?:later|now)|months? (?:later|now)|still (?:waiting|haven'?t|no)|takes? (?:forever|weeks|months)|backlog|queue"),
    "unclear": ("Unclear rules or what to do next", r"don'?t know (?:what|how|where|who)|not sure (?:what|how|where|who)|what (?:can|should) i do|what are my (?:rights|options)|is (?:this|it) legal|confus\w*|no idea|where (?:do|can) i (?:report|complain|file)|who do i (?:contact|call|ask)"),
    "proof": ("No record or proof", r"no (?:proof|evidence|record|receipt|paper ?trail)|not in writing|verbal(?:ly)?|never (?:signed|wrote)|can'?t prove|no contract|without (?:a )?(?:receipt|contract|record)"),
    "scam": ("Scam or fraud", r"scam\w*|fraud\w*|fake|phishing|counterfeit|impersonat\w*|duped|conned"),
    "quality": ("Broken, unsafe or poor quality", r"defect\w*|faulty|doesn'?t work|stopped working|unsafe|dangerous|mold|mould|leak\w*|crash\w*|unreliable|poor quality|rotten"),
    "manual": ("Done by hand, no good tool", r"spreadsheet|by hand|manually|copy[- ]?paste|paper ?work|paper forms?|whatsapp group|excel|no (?:tool|app|software|system)|there'?s no (?:way|easy way)|workaround|cobbl\w*"),
    "burnout": ("Overload and burnout", r"burn(?:ed|t)? ?out|overwhelm\w*|exhaust\w*|no time|too much (?:work|to do)|overworked|unpaid|can'?t keep up|stress\w*"),
    "access": ("Cannot get or reach it", r"can'?t (?:find|get|access|reach|book|buy)|unavailable|out of stock|shortage|sold out|no (?:access|appointments?|slots?|supply|stock)|not available|too far|waitlist"),
}
_RE = {k: re.compile(r"\b(?:" + pat + r")\b", re.I) for k, (_, pat) in FAMILIES.items()}


def families(text: str, topic: str = "") -> list[str]:
    """Families a text matches, strongest first (by number of hits). Words the topic itself uses are removed first,
    so a topic like "not returning a deposit" does not put every post in the "refuses" family."""
    for w in sorted({w for w in re.findall(r"[a-z]{4,}", topic.lower())}, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(w[:max(4, len(w) - 3)]) + r"\w*", " ", text, flags=re.I)
    hits = [(len(_RE[k].findall(text)), k) for k in _RE]
    return [k for n, k in sorted(hits, reverse=True) if n]


def label(key: str) -> str:
    return FAMILIES[key][0]
