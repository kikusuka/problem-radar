"""A small labelled set for the relevance filters, built from failures people actually reported.

Each row: (niche, title, text, on_topic). `on_topic` means a human would say the post is about that problem. The filters are
checked on precision (nothing off-topic reaches a ranked list) and on recall for the wide candidate pool (on-topic posts are
not lost). Add a row whenever a live search returns something wrong; that is how this set should grow.
"""
import pytest

from radar import research
from radar import sources as S

LONG = "x " * 260  # pushes a mention beyond the opening of the text

ROWS = [
    # --- mandi price (reported: football transfers and unrelated tech came back)
    ("mandi price", "Onion mandi price crashed again in Lasalgaon", "Farmers say the mandi price for onion fell to Rs 5 per kg, below the cost of production. Frustrating.", True),
    ("mandi price", "How do I check the daily mandi price for tomato?", "Is there an app to check mandi price near me? Agmarknet is confusing and I am struggling to use it.", True),
    ("mandi price", "Arhtiya cuts at the mandi", "Commission agents at the mandi take a cut and the mandi price I get is lower than the price shown online. Unfair.", True),
    ("mandi price", "Striker transfer price hits 180 million", "The club agreed a price with the player's agent in a record football transfer. Fans are frustrated.", False),
    ("mandi price", "Show HN: price tracker for SaaS subscriptions", "A tool to compare the price of software subscriptions. I built it because pricing pages are confusing.", False),
    ("mandi price", "Visiting Mandi in Himachal", "Mandi is a lovely town with temples and trekking. The road was broken and frustrating though.", False),
    ("mandi price", "Rice price at the Tokyo market", "The price of rice at the market in Tokyo went up again, it is painful for families.", False),
    # --- crop insurance (reported: unrelated US insurance and political posts)
    ("crop insurance", "Crop insurance claim rejected after hailstorm", "My wheat crop insurance claim was rejected after the hailstorm and nobody explains why. This is unfair.", True),
    ("crop insurance", "Farmers say crop insurance payouts are delayed", "Small farmers wait months for crop insurance payouts and some never get paid. A real problem.", True),
    ("crop insurance", "Is crop insurance worth it for small farms?", "I farm 3 acres and crop insurance premiums are expensive. Is there a cheaper way to protect against drought?", True),
    ("crop insurance", "US health insurance premiums rise again", "Politicians argue about health insurance premiums while families struggle to pay. Frustrating.", False),
    ("crop insurance", "Auto insurance rates and the election", "Auto insurance rates are a political issue and a painful expense for drivers.", False),
    ("crop insurance", "Senate clashes over the farm bill", "Democrats and Republicans clash over food stamps in the farm bill. The debate is frustrating.", False),
    # --- elder care (reported: carbon emissions and Lambda School appeared via a passing mention)
    ("elder care", "My mom needs elder care and I cannot afford assisted living", "Elder care costs are impossible for our family and I am struggling to find help for my mother.", True),
    ("elder care", "Elder care paperwork is a nightmare", "Anyone know a tool for managing elder care paperwork? The forms are so frustrating.", True),
    ("elder care", "Elder care homes have no way to compare prices", "Comparing elder care prices is a real problem for families and I wish there was a tool.", True),
    ("elder care", "California to require firms to reveal carbon emissions", LONG + "my elderly mother needs elder care and it is a struggle", False),
    ("elder care", "Lambda School leaked documents show poor performance", LONG + "society should take care of their elders, it is frustrating", False),
    ("elder care", "Lawn care tips for spring", "Lawn care is frustrating in spring when the grass will not grow evenly. Any tips?", False),
    ("elder care", "Child care costs keep rising", "Child care costs are unfair and painful for young families.", False),
]


def post(i, title, text):
    return S.Post("hn", f"hn-{i}", title, text, f"https://example.com/{i}", f"user{i}", 5, 3, "2026-01-01", {})


@pytest.mark.parametrize("niche,title,text,on_topic", ROWS)
def test_ranked_results_never_include_an_off_topic_post(niche, title, text, on_topic):
    ranked, _ = research._rank([post(1, title, text)], [niche])
    if not on_topic:
        assert not ranked, f"off-topic post reached top results: {title}"


def test_candidate_pool_precision_and_recall():
    by_niche = {}
    for i, (niche, title, text, on_topic) in enumerate(ROWS):
        by_niche.setdefault(niche, []).append((post(i, title, text), on_topic))
    tp = fp = fn = 0
    misses, leaks = [], []
    for niche, items in by_niche.items():
        got = {p.id for _, p, _ in research._candidates([p for p, _ in items], [niche])}
        for p, on_topic in items:
            if p.id in got and on_topic:
                tp += 1
            elif p.id in got and not on_topic:
                fp += 1
                leaks.append(p.title)
            elif on_topic:
                fn += 1
                misses.append(p.title)
    precision, recall = tp / max(1, tp + fp), tp / max(1, tp + fn)
    assert precision >= 0.85, f"candidate precision {precision:.2f}; leaked: {leaks}"
    assert recall >= 0.85, f"candidate recall {recall:.2f}; missed: {misses}"


# Known limit: the filters are lexical, so a post that describes the topic in different words is not found. `also` and the
# vocabulary in `people_say` are the mitigation today. These are expected to fail; if one starts passing (for example after
# adding embeddings), the strict xfail turns red so the mark and the README can be updated.
PARAPHRASES = [
    ("elder care", "Dad has dementia and the nursing home bill is crushing us", "My father has dementia, I am his only caregiver, and the nursing home fees are crushing the family."),
    ("crop insurance", "PMFBY claim money never reached my account", "My wheat was destroyed by hail, I filed the PMFBY form and the compensation never reached my bank account."),
    ("mandi price", "Traders pay less than MSP at the market yard", "At the market yard traders paid us less than the minimum support rate for onions again."),
]


@pytest.mark.xfail(strict=True, reason="lexical retrieval cannot match a paraphrase; see people_say and the `also` parameter")
@pytest.mark.parametrize("niche,title,text", PARAPHRASES)
def test_paraphrases_are_found_by_the_candidate_pool(niche, title, text):
    p = post(99, title, text)
    assert [x for _, x, _ in research._candidates([p], [niche])]
