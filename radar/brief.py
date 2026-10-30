"""The shape of a finished problem brief, and a check that it follows the rules this server asks the host model to follow.

The server never writes the brief (the host model does). It only says what a brief must contain and checks, deterministically,
that the evidence is real and labelled honestly. It does not score the problem.
"""
from __future__ import annotations

from urllib.parse import urlparse

from . import verify

REQUIRED = {
    "statement": "one sentence: who struggles with what",
    "who": "the people who have it, and where they are",
    "workaround": "what they do about it today (manual steps, spreadsheets, paying someone), or 'none found'",
    "evidence": "list of {claim, url, label} where label is DOCUMENTED or HYPOTHESIS",
    "already_solved": "what check_if_solved found, in your words",
    "who_is_missing": "who this evidence does not hear (see representation_risk)",
    "validation_plan": "who to ask, and 3 questions about the last time it went wrong",
    "kill_criteria": "what answer would show this is not worth building",
}
# Where people write about their own trouble. Evidence from these is a public post, so it is a HYPOTHESIS, never DOCUMENTED.
POST_HOSTS = ("reddit.com", "news.ycombinator.com", "stackoverflow.com", "stackexchange.com", "bsky.app", "gitlab.com", "github.com")

SCHEMA = {
    "fields": REQUIRED,
    "labels": {"DOCUMENTED": "an official record, measurement or paper you cited", "HYPOTHESIS": "supported only by public posts or your own reasoning"},
    "rules": [
        "Cite only URLs this server returned; check_brief tells you which ones it did not.",
        "A public post is HYPOTHESIS evidence however many there are; DOCUMENTED needs an official, measured or paper source.",
        "Existing products show supply, not demand.",
        "Say who is not heard. Say what would change your mind.",
    ],
}


def _host(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.")


def check(brief: dict) -> dict:
    problems: list[str] = []
    warnings: list[str] = []
    brief = brief or {}
    for field in REQUIRED:
        v = brief.get(field)
        if v in (None, "", [], {}):
            problems.append(f"missing: {field} ({REQUIRED[field]})")
    ev = brief.get("evidence") if isinstance(brief.get("evidence"), list) else []
    if brief.get("evidence") and not isinstance(brief.get("evidence"), list):
        problems.append("evidence must be a list of {claim, url, label}")
    claims = []
    for i, e in enumerate(ev, 1):
        if not isinstance(e, dict) or not e.get("claim") or not e.get("url"):
            problems.append(f"evidence[{i}] needs both claim and url")
            continue
        label = str(e.get("label", "")).upper()
        if label not in ("DOCUMENTED", "HYPOTHESIS"):
            problems.append(f"evidence[{i}] has no label: use DOCUMENTED or HYPOTHESIS")
        elif label == "DOCUMENTED" and any(_host(e["url"]).endswith(h) for h in POST_HOSTS):
            problems.append(f"evidence[{i}] is labelled DOCUMENTED but {_host(e['url'])} is a public post: label it HYPOTHESIS")
        claims.append({"claim": e["claim"], "urls": [e["url"]]})
    checked = verify.check_claims(claims) if claims else {"claims": []}
    labels = {e["claim"]: str(e.get("label", "")).upper() for e in ev if isinstance(e, dict) and e.get("claim")}
    for r in checked.get("claims", []):
        url = (r.get("citations") or [{}])[0].get("url", "")
        # Only an official page or paper may be "read elsewhere"; a post link this server never returned is suspect whatever its label.
        documented = labels.get(r["claim"]) == "DOCUMENTED" and not any(_host(url).endswith(h) for h in POST_HOSTS)
        if r["status"] == "url_not_retrieved":
            # An official page or paper read with another tool is expected to be unknown here; a missing post link is not.
            (warnings if documented else problems).append(
                ("not retrieved by this server, confirm it on the page yourself: " if documented else "link was never returned by this server (invented?): ") + r["claim"][:90])
        elif r["status"] == "not_found_in_text":
            problems.append("claim not found in the cited text: " + r["claim"][:90])
        elif r["status"] == "partly_supported":
            warnings.append("claim only partly supported: " + r["claim"][:90])
    urls = {_host(e["url"]) + e["url"] for e in ev if isinstance(e, dict) and e.get("url")}
    if ev and len(urls) < 2:
        warnings.append("only one distinct source: one voice is a lead, not a pattern")
    if ev and not any(str(e.get("label", "")).upper() == "DOCUMENTED" for e in ev if isinstance(e, dict)):
        warnings.append("no DOCUMENTED evidence: say plainly that this rests on public posts")
    return {"ok": not problems, "problems": problems, "warnings": warnings, "claims_checked": checked,
            "how_to_read": "ok means the brief has every field and its cited links and numbers match what the server retrieved. It does not mean the problem is real or worth building."}
