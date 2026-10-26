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
            "help_request",
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



def test_product_showcase_wins_over_failure_terms_in_its_description():
    title = (
        "HybridInfer - Android/Kotlin library for on-device LLM inference "
        "with automatic fallback when local wedges (Apache-2.0)"
    )
    description = (
        "I built this small Android library after seeing local inference crash and stall. "
        "It switches backends when a local model stops responding."
    )
    profile = signal_quality.signal_profile(title + " " + description)
    assert profile["evidence_kind"] == "solution_showcase"
    candidate = post("reddit", "hybridinfer-full", title, description, author="maker")
    ranked, misses = research._rank(
        [candidate],
        ["Android local LLM crashes out of memory"],
        require_pain=True,
        enforce_constraints=False,
    )
    assert ranked == []
    assert any(item[1].id == "hybridinfer-full" for item in misses)


def test_source_query_rotation_spreads_alternates_under_existing_caps(monkeypatch):
    monkeypatch.setattr(S, "startup_request_cost", lambda provider: 0)
    jobs = research.plan(
        "offline AI assistant for low-end Android phones",
        lens="software",
        sources=["reddit", "hn", "se", "gitlab", "github"],
        also=["local LLM", "offline voice assistant", "low RAM", "on-device AI"],
    )
    selected = research._limit_jobs(jobs)
    by_source = {}
    for job in selected:
        by_source.setdefault(job.source, []).append(job.query)

    assert len(selected) <= research.MAX_JOBS_PER_REQUEST
    assert all(len(qs) <= research.provider_budget(research.SOURCE_PROVIDER_GROUP.get(source, source)) for source, qs in by_source.items()
               if source not in {"reddit_community"})
    # The same exact broad alternate should not consume every source's second slot.
    alternates = [qs[1] for source, qs in by_source.items() if len(qs) > 1]
    assert len(set(alternates)) >= 3
    assert all(qs[0] == "offline ai assistant low-end android phones" for qs in by_source.values())


def test_direct_search_rotates_alternate_queries_per_source(monkeypatch):
    query = "Android local LLM crashes out of memory"
    calls = {name: [] for name in ("reddit", "github", "hn")}

    def fake(name):
        def search(q, limit=20, **kwargs):
            calls[name].append(q)
            return S.Result([])
        return search

    monkeypatch.setattr(S, "startup_request_cost", lambda provider: 0)
    monkeypatch.setenv("GITHUB_TOKEN", "t")  # with a token GitHub's budget allows alternates
    for name in calls:
        monkeypatch.setitem(S.SOURCES, name, fake(name))
    result = research.search(query, sources=["reddit", "github", "hn"], limit=5)

    assert all(query in qs for qs in calls.values())
    second_queries = [qs[1] for qs in calls.values() if len(qs) > 1]
    assert len(set(second_queries)) == 3
    assert len(result["query_variants_scheduled"]) >= 4



def test_tutorial_title_is_not_mislabeled_as_failure_report():
    title = (
        "Everything I learned building on-device AI into a React Native app -- "
        "LLMs, Stable Diffusion, Whisper, and Vision"
    )
    body = (
        "I spent some time building an app that runs LLMs, image generation, voice "
        "transcription, and vision AI entirely on-device. Here's what I wish someone "
        "had told me before I started. I discuss crashes, memory errors, and how to debug them."
    )
    profile = signal_quality.signal_profile(title + " " + body)
    assert profile["evidence_kind"] == "technical_tutorial"
    assert profile["promotional"] is False


def test_tutorial_with_failure_vocabulary_is_not_ranked_as_a_complaint():
    title = (
        "Everything I learned building on-device AI into a React Native app -- "
        "LLMs, Stable Diffusion, Whisper, and Vision"
    )
    body = (
        "I built an app that runs local LLMs. I explain memory errors and crashes I "
        "encountered while testing, and what I learned debugging those failures."
    )
    tutorial = post("reddit", "ondevice-tutorial", title, body, author="author")
    ranked, misses = research._rank(
        [tutorial],
        ["Android local LLM crashes out of memory"],
        require_pain=True,
        enforce_constraints=False,
    )
    assert ranked == []
    assert any(item[1].id == "ondevice-tutorial" for item in misses)


def test_local_llm_query_rejects_android_memory_bug_without_llm_evidence():
    query = "Android local LLM crashes out of memory"
    unrelated = (
        "Opening large Markdown files in the mobile preview panel causes severe UI lag, "
        "freezing, and white-screen crashes on iOS and Android devices."
    )
    unrelated_model = (
        "Packaging compiled assets and application resources causes Android app crashes and "
        "memory errors after installation. The report focuses on app packaging, not inference."
    )
    real_topic = (
        "The Android app running a local LLM crashes with an out-of-memory error after longer prompts."
    )
    assert not pain.topic_fit(query, unrelated)
    assert not pain.topic_fit(query, unrelated_model)
    assert pain.topic_fit(query, real_topic)


def test_topical_core_anchor_keeps_relevant_complaint_and_rejects_adjacent_bug():
    query = "Android local LLM crashes out of memory"
    unrelated = post(
        "github",
        "android-markdown-preview",
        "Large Markdown preview freezes on Android",
        "Opening large Markdown files on Android causes UI lag, freezing and white-screen crashes.",
        author="reporter",
    )
    complaint = post(
        "reddit",
        "android-local-llm-oom",
        "Android local LLM keeps crashing with out-of-memory errors",
        "My Android local LLM keeps crashing after longer prompts. It freezes with an out-of-memory error.",
        author="reporter2",
    )
    ranked, _ = research._rank(
        [unrelated, complaint],
        [query],
        require_pain=True,
        enforce_constraints=False,
    )
    assert [item[1].id for item in ranked] == ["android-local-llm-oom"]


def test_strong_failure_report_cues_still_classify_firsthand_memory_bug():
    text = "Tasker keeps crashing due to low memory and fails to allocate a small buffer."
    assert signal_quality.signal_profile(text)["evidence_kind"] == "technical_failure_report"
