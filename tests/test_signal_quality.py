from radar import pain, research, signal_quality
from radar import sources as S


def test_explicit_multiword_pain_phrase_can_pass_gate():
    assert signal_quality.signal_profile("This workflow is too slow.")[ "explicit_pain"] is True
    assert pain.looks_like_pain("This workflow is too slow.")
    # A generic one-word cue remains insufficient on its own.
    assert not pain.looks_like_pain("The app is broken.")


def test_signal_profile_exposes_tier_and_category():
    profile = signal_quality.signal_profile(
        "I'm frustrated with invoice exports and looking for a tool."
    )
    assert profile["counts"]["pain_point"] >= 1
    assert profile["counts"]["ask"] >= 1
    assert any(item["category"] == "emotion" for item in profile["matches"])
    assert profile["weighted_score"] > 0


def test_maker_posts_are_marked_and_signal_confidence_reduced():
    profile = signal_quality.signal_profile(
        "I built an invoice app for a frustrating workflow; check it out and join the waitlist."
    )
    assert profile["promotional"] is True
    assert profile["matches"]
    assert all(item["confidence"] == 0.5 for item in profile["matches"])


def test_ordinary_first_person_complaint_is_not_promotion():
    profile = signal_quality.signal_profile(
        "I'm frustrated with manual invoice matching. It takes forever."
    )
    assert profile["promotional"] is False
    assert all(item["confidence"] == 1.0 for item in profile["matches"])


def test_vendor_guides_and_software_roundups_get_non_demand_evidence_kind():
    examples = [
        "What's the Best Residential HVAC Invoicing Software For Billing and Payments? "
        "Over the past month, I spent some time testing out five different options.",
        "How Healthcare Teams Can Use AP Automation Software. "
        "The hidden cost of manual AP in healthcare; what to look for in automation software.",
        "Automated Bank Reconciliation: A Complete Guide. "
        "Manual vs. automated bank reconciliation and the benefits of software.",
        "7 Of The Best Subscription Management Software Solutions For B2B SaaS Startups. "
        "Key takeaways and pricing comparisons.",
    ]

    for text in examples:
        profile = signal_quality.signal_profile(text)
        assert profile["evidence_kind"] == "vendor_editorial", (text, profile["evidence_kind"])
        assert profile["promotional"] is False


def test_compact_research_results_include_traceable_signal_annotations():
    post = S.Post(
        "reddit", "signal-test", "Invoice export is too slow",
        "I'm frustrated with manually copying invoices into spreadsheets.",
        "https://example.com/invoice", "person", 2, 1, "2026-10-01",
    )
    compact = research._compact(post, 0.9, f"{post.title} {post.text}")
    assert "signal_evidence" in compact
    assert compact["signal_evidence"]["counts"]["pain_point"] >= 1
    assert compact["signal_evidence"]["self_promotional"] is False


def test_launch_announcements_without_i_built_are_flagged_as_promotional():
    profile = signal_quality.signal_profile(
        "Big Milestone! Excited to announce our app is live and available to download. "
        "Download directly from the App Store today."
    )
    assert profile["promotional"] is True


def test_non_promotional_first_person_technical_complaint_stays_independent():
    profile = signal_quality.signal_profile(
        "My Android local model keeps crashing with an out-of-memory error. "
        "This is frustrating and freezes after every prompt."
    )
    assert profile["promotional"] is False
    assert profile["counts"]["pain_point"] >= 1


def test_spending_mentions_alone_do_not_establish_pain():
    assert not pain.looks_like_pain(
        "I pay $20 per month for a local LLM subscription and use a Mac."
    )


def test_technical_failure_aliases_require_failure_evidence():
    query = "Android local LLM crashes out of memory"
    assert not pain.topic_fit(query, "Android local LLM features for offline chat")
    assert pain.topic_fit(query, "Android local LLM crashes with an OOM error")
