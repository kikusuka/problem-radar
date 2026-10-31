"""Region packs: where documented evidence lives, and how people there talk about a topic.

Public posts show who complains; they cannot say how common or how severe a problem is. For that you need official data,
surveys and studies. This server does not query most of them, so a pack says plainly where to look and in what words, and
the chat model uses its own web tools on them. Nothing here is a finding. Every source is tagged `queried_by_server: False`
and `checked: False`: it exists and measures what the line says, but its machine-readable access has not been verified here.
Only what the model actually reads there may be called DOCUMENTED. Add a region by adding an entry; keep it short and true.
"""
from __future__ import annotations

import re


def S(name: str, url: str, measures: str, domains: list[str], note: str = "") -> dict:
    row = {"name": name, "url": url, "measures": measures, "domains": domains, "queried_by_server": False, "checked": False}
    if note:
        row["note"] = note
    return row


PACKS = {
    "IN": {
        "sources": [
            S("Agmarknet", "https://agmarknet.gov.in", "daily market arrivals and prices of farm produce at mandis", ["agriculture"]),
            S("e-NAM", "https://enam.gov.in", "national electronic agriculture market: trades and prices", ["agriculture"]),
            S("PM-KISAN", "https://pmkisan.gov.in", "income-support scheme for farmer families: coverage and payments", ["agriculture"]),
            S("PMFBY", "https://pmfby.gov.in", "crop insurance scheme: enrolment, claims", ["agriculture"]),
            S("ICAR", "https://icar.org.in", "agricultural research council: studies, crop and farm technology", ["agriculture"]),
            S("MoSPI surveys (NSS, PLFS)", "https://mospi.gov.in", "national sample surveys, including agricultural households and labour force", ["agriculture", "work", "health", "elder care", "education"]),
            S("data.gov.in", "https://data.gov.in", "Open Government Data platform: datasets from ministries", ["agriculture", "health", "education", "transport", "elder care", "work"],
              "its daily mandi-price dataset page said no API exists for that resource and stated no licence when last read (2026-10-29); check each dataset before relying on it"),
            S("CEDA Agri Market Data", "https://agmarknet.ceda.ashoka.edu.in", "research mirror of Agmarknet prices, cleaned for analysis (Ashoka University)", ["agriculture"],
              "a third-party research mirror, not the official source; read its README for coverage and terms"),
            S("CPGRAMS", "https://pgportal.gov.in", "central public grievance portal: complaints by ministry and category", ["any"]),
            S("NFHS", "https://rchiips.org/nfhs", "National Family Health Survey: health, nutrition, household indicators", ["health", "elder care"]),
            S("LASI", "https://www.iipsindia.ac.in/lasi", "Longitudinal Ageing Study in India: health, income and care of people aged 45+", ["elder care", "health"]),
            S("Road accident reports (MoRTH)", "https://morth.nic.in", "road accidents and deaths by state", ["transport"]),
            S("NCRB", "https://ncrb.gov.in", "crime, accident and suicide statistics", ["safety", "transport"]),
        ],
        "terms": {
            "agriculture": ["mandi", "MSP minimum support price", "kisan", "kharif rabi", "APMC", "fasal bima", "arhtiya commission agent"],
            "elder care": ["old age home", "vridh ashram", "senior citizens", "pension", "maintenance of parents"],
            "health": ["PHC primary health centre", "ASHA worker", "Ayushman Bharat", "government hospital"],
            "education": ["board exams", "coaching", "scholarship", "government school"],
            "transport": ["potholes", "auto rickshaw", "bus pass", "road accident"],
        },
        "laws": {"elder care": ["Maintenance and Welfare of Parents and Senior Citizens Act, 2007"]},
    },
}

# Local names that fit a SUB-topic, so a search is helped and not polluted ("mandi" would flood a crop-insurance search).
# Used only when the caller passed no local wording of its own. Each entry: (words in the niche that trigger it, terms to add).
TOPIC_TERMS = {
    "IN": {
        "agriculture": [(r"insur|claim|crop loss|compensat", ["PMFBY", "fasal bima"]),
                        (r"price|sell|market|mandi|msp", ["mandi price", "MSP"]),
                        (r"loan|credit|debt", ["Kisan Credit Card", "farm loan waiver"])],
        "elder care": [(r".", ["old age home", "senior citizens"])],
        "health": [(r"insur|claim|bill|cost", ["Ayushman Bharat"]), (r"rural|village|clinic|doctor", ["PHC primary health centre", "ASHA worker"])],
        "education": [(r"scholar|fee|fund", ["scholarship portal"]), (r"exam|board|coach|test", ["board exams", "coaching"])],
        "transport": [(r"road|pothole|traffic", ["potholes"]), (r"bus|pass|commut", ["bus pass"])],
    },
}


def auto_terms(region: dict | None, niche: str, limit: int = 2) -> list[str]:
    """Curated local wording that fits the niche's sub-topic, or [] when none is known. Never guesses outside a known pack."""
    if not region or region.get("code") not in TOPIC_TERMS:
        return []
    out: list[str] = []
    table = TOPIC_TERMS[region["code"]]
    for dom in domains_of(niche):
        for trigger, terms in table.get(dom, []):
            if re.search(trigger, niche, re.I):
                out += [t for t in terms if t.casefold() not in niche.casefold() and t not in out]
        if out:
            break
    return out[:limit]


DOMAIN_WORDS = {
    "agriculture": r"agri|farm|crop|mandi|harvest|irrigat|fertili[sz]|seed|livestock|dairy|kisan|soil",
    "elder care": r"elder|senior|aged|ageing|aging|old age|dementia|geriatric",
    "health": r"health|hospital|clinic|doctor|medic|disease|nutrition",
    "education": r"school|student|educat|exam|teacher|college|scholar",
    "transport": r"road|traffic|transport|bus|pothole|commut|vehicle",
    "work": r"job|worker|labou?r|wage|employ|gig",
    "safety": r"safety|crime|accident|harass",
}


def domains_of(text: str) -> list[str]:
    return [d for d, rx in DOMAIN_WORDS.items() if re.search(rx, text or "", re.I)]


def pack_for(region: dict | None, niche: str, also: list[str] | None = None) -> dict | None:
    """The part of a region's pack that fits the topic, or None when there is no pack. The server never guesses a region."""
    if not region or region.get("code") not in PACKS:
        return None
    pack = PACKS[region["code"]]
    doms = domains_of(" ".join([niche, *(also or [])]) )
    keep = [s for s in pack["sources"] if (set(s["domains"]) & set(doms)) or "any" in s["domains"]] if doms else [s for s in pack["sources"] if "any" in s["domains"]]
    terms = {d: pack["terms"][d] for d in doms if d in pack["terms"]}
    laws = {d: pack["laws"][d] for d in doms if d in pack.get("laws", {})}
    out = {
        "region": region["name"],
        "topic_areas": doms,
        "documented_evidence_lives_here": keep,
        "local_wording_to_try": terms,
        "how_to_use": ("This server did not query these. Open them with your own web tools, cite only what you actually read there, and label it "
                       "DOCUMENTED; everything from public posts stays a HYPOTHESIS until it is checked against one of these. Pass local wording in `also`."),
    }
    if laws:
        out["laws_and_policies"] = laws
    return out
