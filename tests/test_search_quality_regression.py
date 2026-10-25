import pytest

from radar import pain, research, signal_quality
from radar import sources as S


def post(source, ident, title, text, author="user", score=1, comments=0):
    return S.Post(
        source,
        ident,
        title,
        text,
        f"https://example.com/{ident}",
        author,
        score,
        comments,
        "2026-10-24",
    )


@pytest.mark.parametrize(
    ("query", "expected_fragment"),
    [
        ("Android local LLM crashes out of memory", "OOM"),
        ("Android local LLM keeps crashing", "freezes"),
    ],
)
def test_technical_query_expansion_swaps_failure_cue_and_preserves_topic(query, expected_fragment):
    variants = pain.query_expansions(query)
    assert variants
    assert expected_fragment.casefold() in variants[0].casefold()
    assert all("android" in q.casefold() and "local llm" in q.casefold() for q in variants)


def test_general_expansions_keep_platform_and_resource_constraints():
    query = "offline AI assistant for low-end Android phones"
    variants = pain.query_expansions(query)
    assert "offline AI chatbot for low-end Android phones" in variants
    assert any("without internet" in q for q in variants)
    assert any("low-RAM" in q for q in variants)
    assert all(not pain.missing_constraints(query, candidate) for candidate in variants)


@pytest.mark.parametrize(
    ("text", "expected_kind"),
    [
        (
            "My Android local LLM keeps crashing with an OOM error after longer prompts.",
            "technical_failure_report",
        ),
        (
            "Big Milestone! Excited to announce our Android app is live. Download it today.",
            "product_announcement",
        ),
        (
            "HybridInfer - Android/Kotlin library for on-device LLM inference with automatic fallback when local wedges (Apache-2.0)",
            "solution_showcase",
        ),
        (
            "I manually copy invoice data into a spreadsheet every week.",
            "workaround_or_manual_process",
        ),
        (
            "How do I stop this Android LLM from freezing?",
            "technical_failure_report",
        ),
        (
            "Tool A versus Tool B for invoice exports",
            "product_comparison",
        ),
    ],
)
def test_evidence_classification_regression_cases(text, expected_kind):
    assert signal_quality.signal_profile(text)["evidence_kind"] == expected_kind


def test_solution_showcase_is_not_ranked_as_independent_complaint():
    query = "Android local LLM crashes out of memory"
    showcase = post(
        "reddit",
        "hybridinfer-showcase",
        "HybridInfer - Android/Kotlin library for on-device LLM inference with automatic fallback when local wedges (Apache-2.0)",
        "An Android/Kotlin library for on-device LLM inference with automatic fallback when local inference wedges.",
        author="maker",
        score=50,
        comments=30,
    )
    complaint = post(
        "reddit",
        "android-oom-complaint",
        "Android local LLM keeps crashing with out-of-memory errors",
        "My Android local LLM keeps crashing after longer prompts. It freezes with an out-of-memory error and is frustrating to use.",
        author="complainant",
        score=2,
        comments=5,
    )
    ranked, misses = research._rank(
        [showcase, complaint],
        [query],
        require_pain=True,
        enforce_constraints=False,
    )
    assert [item[1].id for item in ranked] == ["android-oom-complaint"]
    assert any(item[1].id == "hybridinfer-showcase" for item in misses)


def test_evidence_summary_counts_sources_and_handles_without_claiming_identity():
    posts = [
        post("reddit", "r1", "Complaint A", "frustrating issue", author="same-handle"),
        post("reddit", "r2", "Complaint B", "frustrating issue", author="same-handle"),
        post("github", "g1", "Bug report", "crashes constantly", author="same-handle"),
    ]
    summary = research._evidence_summary(posts)
    assert summary["qualifying_post_count"] == 3
    assert summary["distinct_source_count"] == 2
    assert summary["distinct_author_handles"] == 2
    assert summary["corroborated_across_sources"] is True
    assert "not identity-checked" in summary["interpretation"]


def test_search_diagnostics_distinguish_budget_limits_from_empty_evidence():
    limited = research._search_diagnostics(
        0,
        0,
        {
            "reddit": {"ok": 1, "state": "partial", "request_limited": True},
            "hn": {"ok": 1, "state": "ok"},
        },
        ["Android local LLM", "Android local LLM OOM"],
    )
    assert limited["status"] == "coverage_limited"
    assert "not evidence that the problem is absent" in limited["interpretation"]
    assert limited["scheduled_query_variants"] == ["Android local LLM", "Android local LLM OOM"]

    adjacent = research._search_diagnostics(0, 2, {"reddit": {"ok": 1, "state": "ok"}}, [])
    assert adjacent["status"] == "related_candidates_only"

    found = research._search_diagnostics(3, 0, {"reddit": {"ok": 1, "state": "ok"}}, [])
    assert found["status"] == "qualifying_results_found"


def test_search_schedules_expansions_inside_existing_provider_budget(monkeypatch):
    query = "Android local LLM crashes out of memory"
    calls = []

    def fake_search(q, limit=20, **kwargs):
        calls.append(q)
        return S.Result([])

    monkeypatch.setattr(S, "startup_request_cost", lambda provider: 0)
    monkeypatch.setitem(S.SOURCES, "reddit", fake_search)
    out = research.search(query, sources=["reddit"], limit=5)

    assert set(calls) == set(out["query_variants_scheduled"])
    assert query in calls
    assert len(calls) <= research.MAX_REQUESTS_PER_PROVIDER_PER_CALL
    assert out["search_diagnostics"]["status"] in {"coverage_limited", "no_qualifying_evidence"}
