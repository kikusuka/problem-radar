"""Region awareness. Problem Radar is worldwide by default; a region narrows and biases the search when the person asks.

The chatting model decides the region from the conversation (and the person can change it), then passes it in.
We never guess it on the server. A region does three things:
  1. adds that country's own communities (subreddits) and puts the country in some queries,
  2. runs official-data sources only where they apply (UK petitions for the UK, NYC 311 and FDA for the US),
  3. says plainly when there is no official-data connector for that place, instead of staying silent.
"""
from __future__ import annotations

import re

# code: (name, aliases, subreddits)
REGIONS = {
    "US": ("United States", ["usa", "united states", "america", "u.s.", "us"], ["AskAnAmerican", "personalfinance"]),
    "GB": ("United Kingdom", ["uk", "united kingdom", "britain", "great britain", "england", "scotland", "wales", "gb"], ["unitedkingdom", "CasualUK"]),
    "IN": ("India", ["india", "indian", "in"], ["india", "IndianStudents"]),
    "CA": ("Canada", ["canada", "canadian", "ca"], ["canada", "AskACanadian"]),
    "AU": ("Australia", ["australia", "australian", "au"], ["australia", "AskAnAustralian"]),
    "DE": ("Germany", ["germany", "german", "de"], ["germany", "de"]),
    "FR": ("France", ["france", "french", "fr"], ["france"]),
    "BR": ("Brazil", ["brazil", "brasil", "brazilian", "br"], ["brasil"]),
    "NG": ("Nigeria", ["nigeria", "nigerian", "ng"], ["Nigeria"]),
    "ZA": ("South Africa", ["south africa", "za"], ["southafrica"]),
    "KE": ("Kenya", ["kenya", "kenyan", "ke"], ["Kenya"]),
    "PH": ("Philippines", ["philippines", "filipino", "ph"], ["Philippines"]),
    "PK": ("Pakistan", ["pakistan", "pakistani", "pk"], ["pakistan"]),
    "ID": ("Indonesia", ["indonesia", "indonesian", "id"], ["indonesia"]),
    "EU": ("European Union", ["eu", "europe", "european union"], ["europe"]),
}

# Official-data sources and where they apply. Anything not listed here is worldwide.
SOURCE_REGIONS = {"petitions": {"GB"}, "nyc311": {"US"}, "fda_devices": {"US"}}
SOURCE_NOTE = {"petitions": "UK Parliament petitions", "nyc311": "NYC 311 complaints", "fda_devices": "FDA device reports"}


def resolve(text: str | None) -> dict | None:
    """'India', 'in', 'UK', 'united kingdom' -> {'code','name','subreddits'}. Unknown text -> a free-form region."""
    t = (text or "").strip()
    if not t or t.lower() in ("world", "worldwide", "global", "any", "all"):
        return None
    low = re.sub(r"\s+", " ", t.lower())
    for code, (name, aliases, subs) in REGIONS.items():
        if low == code.lower() or low == name.lower() or low in aliases:
            return {"code": code, "name": name, "subreddits": list(subs)}
    return {"code": "", "name": t[:40], "subreddits": []}  # a place we have no table for; still biases queries


def applies(source: str, region: dict | None) -> bool:
    """Official-data sources run only in their region. With no region they still run (worldwide default)."""
    where = SOURCE_REGIONS.get(source)
    return not where or not region or region["code"] in where


def coverage_note(region: dict | None, used: list[str]) -> str:
    if not region:
        return ""
    official = [SOURCE_NOTE[s] for s in used if s in SOURCE_NOTE]
    base = f"Region: {region['name']}. Community sources were searched with {region['name']} added"
    base += f" and its own communities (r/{', r/'.join(region['subreddits'])})." if region["subreddits"] else "."
    if official:
        return base + " Official data used: " + ", ".join(official) + "."
    return (base + f" There is no official-data connector for {region['name']} yet (those exist only for the UK and the US), so "
            "evidence is community and paper based. Run the web search suggestions, which include the country, and use search_pain with local words.")
