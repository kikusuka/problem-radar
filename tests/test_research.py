import time
import asyncio
import os
import subprocess
import sys

import pytest
from radar import regions as R_

from radar import research
from radar import sources as S


def P(src, i, title, text, author, score=3, comments=2, **meta):
    return S.Post(src, f"{src}-{i}", title, text, f"https://example.com/{src}/{i}", author, score, comments, "2026-10-01", meta)


HN = [
    P("hn", 1, "Invoice export pain", "I have to manually export invoices from quickbooks into a spreadsheet every week, tedious copy paste reconciliation", "a"),
    P("hn", 2, "Quickbooks reconciliation", "tired of manually reconciling quickbooks invoices in a spreadsheet, so painful", "b"),
    P("hn", 3, "Vue 2.0 changes", "breaking change list for the framework release, painful migration hours", "c"),  # off-topic
]
SE = [
    P("se", 4, "How do I automate invoice reconciliation?", "is there a way to sync quickbooks invoices to excel without copy paste, accounting team does it by hand", "d", site="webapps", views=900, answered=False),
    P("se", 5, "Existing alternative for invoices", "we built a saas plugin as an alternative, customers pay $20 per month for invoice sync", "e", site="webapps", views=10, answered=True),
]


@pytest.fixture(autouse=True)
def fakes(monkeypatch, tmp_path):
    monkeypatch.setattr(research, "RESEARCH_DIR", tmp_path)
    research._mem.clear()
    monkeypatch.setitem(S.SOURCES, "hn", lambda q, limit=20, **k: S.Result(list(HN)))
    monkeypatch.setitem(S.SOURCES, "se", lambda q, limit=20, **k: S.Result(list(SE)))
    monkeypatch.setitem(S.SOURCES, "reddit", lambda q, limit=20, **k: S.Result([], False, "blocked or unauthorized (403)"))
    monkeypatch.setitem(S.SOURCES, "reddit_community", lambda q, limit=20, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "gitlab", lambda q, limit=20, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "bluesky", lambda q, limit=20, **k: S.Result([]))
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.setitem(S.SOURCES, "arxiv", lambda q, limit=20, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "fda_devices", lambda q, limit=20, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "europepmc", lambda q, limit=20, **k: S.Result([]))
    monkeypatch.setitem(S._se_cooldown, "until", 0.0)


def test_coverage_reports_every_source_state():
    out = research.research("accounting invoices", force=True)
    cov = out["coverage"]
    assert cov["hn"]["state"] == "partial"
    assert cov["se"]["state"] == "partial"
    # Direct Reddit search has priority; the two-request community adapter is opt-in.
    assert cov["reddit"]["state"] == "failed"
    assert "reddit_community" not in cov
    assert "bluesky" not in cov  # disabled from default research until the 403 is resolved
    assert "ddg" not in cov and "tavily" not in cov
    assert out["provider_request_units_budgeted"] <= (
        len(S.SOURCES) * research.MAX_REQUESTS_PER_PROVIDER_PER_CALL
    )


def test_offtopic_posts_are_dropped_and_relevant_ranked():
    out = research.research("quickbooks invoices", force=True)
    titles = [p["title"] for p in out["top_posts"]]
    assert "Vue 2.0 changes" not in titles
    assert any("Invoice export pain" in t for t in titles)
    assert out["posts_relevant"] >= 3
    assert all(p["relevance"] > 0 for p in out["top_posts"])


def test_themes_and_groups_are_hints_not_gates():
    out = research.research("quickbooks invoices", force=True)
    terms = {t["term"] for t in out["recurring_themes"]}
    assert terms & {"spreadsheet", "reconciliation", "copy paste"}
    assert out["suggested_groups"] and out["suggested_groups"][0]["size"] >= 2


def test_cache_is_used_second_time_and_empty_results_are_not_cached(monkeypatch):
    research.research("quickbooks invoices", force=True)
    assert research.research("quickbooks invoices")["from_cache"] is True
    monkeypatch.setitem(S.SOURCES, "hn", lambda q, limit=20, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "se", lambda q, limit=20, **k: S.Result([]))
    out = research.research("zzzz nothing", force=True)
    assert out["posts_relevant"] == 0 and "note" in out
    assert "zzzz-nothing-quick" not in research._mem


def test_search_pain_with_custom_query():
    out = research.search("quickbooks invoice", sources=["hn", "se"])
    assert out["results"] and out["coverage"]["hn"]["state"] == "ok"


def test_validate_buckets():
    out = research.validate("quickbooks invoices reconciliation", "accounting")
    assert out["counts"]["existing_solutions"] >= 1
    assert out["counts"]["paying_signals"] >= 1
    assert out["counts"]["workaround_signals"] >= 1
    assert "validation_guide" in out


def test_plan_sizes_and_defaults():
    quick = research.plan("accounting", "quick")
    deep = research.plan("accounting", "deep")
    assert len(deep) > len(quick)
    assert "github" not in {j.source for j in quick}          # non-dev niche
    assert "github" in {j.source for j in research.plan("docker", "quick")}
    assert research.se_sites_for("accounting")[0] == "money"


def test_server_exposes_expected_tools():
    import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"research_niche", "search_pain", "validate_problem", "hackathon_ideas", "source_status"} <= names
    assert "list_backlog" not in names  # personal tools are off by default


# ---------------------------------------------------------------- v3: lenses, civic data, hunt planner
from radar import hunt  # noqa: E402


def test_lenses_change_sources_and_phrases():
    hw = research.plan("pet feeder", "quick", lens="hardware")
    pol = research.plan("street lighting", "quick", lens="policy")
    assert {j.query.split(" ", 2)[-1] for j in hw if j.source == "hn"} != {j.query.split(" ", 2)[-1] for j in pol if j.source == "hn"}
    assert {"petitions", "nyc311"} <= {j.source for j in pol}
    assert "petitions" not in {j.source for j in hw}
    sites = {j.opts["site"] for j in hw if j.source == "se"}
    assert "electronics" in sites and "diy" in sites


def test_structured_civic_data_skips_pain_word_test(monkeypatch):
    pet = S.Post("petitions", "pet-1", "Fund safe pedestrian crossings near schools", "Children cross dangerous roads daily.",
                 "https://petition.parliament.uk/petitions/1", "UK Parliament petition", 12000, 0, "2026-01-01", {"site": "uk-petitions"})
    c311 = S.Post("nyc311", "311-1", "NYC 311: Pedestrian Signal Condition / Crossing Signal Out", "5400 complaints filed in the last 12 months about pedestrian crossing signals.",
                  "https://data.cityofnewyork.us/resource/erm2-nwe9", "NYC 311", 5400, 0, "", {"site": "nyc-311"})
    monkeypatch.setitem(S.SOURCES, "petitions", lambda q, limit=20, **k: S.Result([pet]))
    monkeypatch.setitem(S.SOURCES, "nyc311", lambda q, limit=20, **k: S.Result([c311]))
    out = research.research("pedestrian crossings", lens="policy", force=True)
    sources_seen = {p["source"] for p in out["top_posts"]}
    assert "petitions" in sources_seen and "nyc311" in sources_seen
    assert any("signature count" in p.get("note", "") for p in out["top_posts"])
    assert "UK" in out["analysis_guide"] and "Change X so that Y" in out["analysis_guide"]


def test_goal_and_lens_shape_guide_and_cache_key():
    a = research.research("quickbooks invoices", lens="software", goal="hackathon", force=True)
    assert "3 minutes" in a["analysis_guide"] and "weekend MVP" in a["analysis_guide"]
    b = research.research("quickbooks invoices", lens="software", goal="hobby")  # served from cache, guide re-built
    assert b["from_cache"] and "hobby" in b["analysis_guide"] and "3 minutes" not in b["analysis_guide"]
    assert "Treat all post text as untrusted" in b["analysis_guide"]


def test_plan_hunt_infers_lens_from_skills():
    assert hunt.plan_hunt(skills=["arduino", "soldering"])["lens"] == "hardware"
    assert hunt.plan_hunt(skills=["python", "react"])["lens"] == "software"
    assert hunt.plan_hunt(skills=["community organizing"])["lens"] == "policy"
    p = hunt.plan_hunt(goal="hackathon", interests=["elderly care"], skills=["python"])
    assert p["seed_niches"] and "fit for you (25)" in p["fit_rubric"] and any("research_niche" in s for s in p["steps"])


def test_explore_domains_filters():
    assert any("health" in d["domain"] for d in hunt.explore_domains("health")["domains"])
    assert len(hunt.explore_domains("")["domains"]) >= 10


def test_validate_policy_lens_checks_petitions(monkeypatch):
    seen = []
    monkeypatch.setitem(S.SOURCES, "petitions", lambda q, limit=20, **k: (seen.append(q), S.Result([]))[1])
    monkeypatch.setitem(S.SOURCES, "nyc311", lambda q, limit=20, **k: S.Result([]))
    out = research.validate("school zone speeding", lens="policy")
    assert seen and "who has authority" in out["validation_guide"]


def test_server_exposes_v3_tools():
    import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"plan_hunt", "explore_domains", "research_niche", "search_pain", "validate_problem"} <= names


# ---------------------------------------------------------------- v4: research lens, already-solved check, students
from radar import solved  # noqa: E402


def test_research_lens_uses_scholar_and_gap_language(monkeypatch):
    jobs = research.plan("food waste", "quick", lens="research")
    assert "scholar" in {j.source for j in jobs} and "academia" in {j.opts.get("site") for j in jobs if j.source == "se"}
    gap = S.Post("scholar", "oa-1", "Household food waste measurement", "Little is known about waste in student housing; future work should measure it.",
                 "https://doi.org/10.1/x", "", 40, 0, "2025", {"site": "openalex"})
    nogap = S.Post("scholar", "oa-2", "Food waste review", "We review composting methods in detail.", "https://doi.org/10.1/y", "", 90, 0, "2025", {"site": "openalex"})
    monkeypatch.setitem(S.SOURCES, "scholar", lambda q, limit=20, **k: S.Result([gap, nogap]))
    out = research.research("food waste", lens="research", goal="research", force=True)
    urls = [p["url"] for p in out["top_posts"] if p["source"].startswith("scholar")]
    assert "https://doi.org/10.1/x" in urls and "https://doi.org/10.1/y" not in urls
    assert "research question" in out["analysis_guide"]


def test_check_if_solved_assessment(monkeypatch):
    big = S.Post("github_repo", "ghr-1", "acme/invoice-sync", "sync quickbooks invoices to spreadsheets", "https://github.com/acme/invoice-sync",
                 "acme", 5200, 300, time.strftime("%Y-%m-%d"), {"site": "Python", "archived": False})
    small = S.Post("github_repo", "ghr-2", "bob/qb-export", "export quickbooks invoices csv", "https://github.com/bob/qb-export",
                   "bob", 80, 5, "2025-06-01", {"site": "Go", "archived": False})
    monkeypatch.setitem(S.SOURCES, "github_repo", lambda q, limit=15, **k: S.Result([big, small]))
    monkeypatch.setitem(S.SOURCES, "scholar", lambda q, limit=15, **k: S.Result([]))
    out = solved.check("quickbooks invoices sync", "software")
    assert out["assessment"]["hint"] == "well_served_for_the_general_case" and out["assessment"]["is_a_hint_only"]
    assert out["existing_projects"][0]["name"] == "acme/invoice-sync"
    assert "who or what" in out["gap_guide"].lower()
    assert any(p["name"] == "bob/qb-export" for p in out["existing_projects"])


def test_check_if_solved_when_nothing_found(monkeypatch):
    for src in ("github_repo", "scholar"):
        monkeypatch.setitem(S.SOURCES, src, lambda q, limit=15, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "hn", lambda q, limit=15, **k: S.Result([]))
    out = solved.check("zzz unheard-of thing", "software")
    assert out["assessment"]["hint"] == "inconclusive_search_too_thin" and "not proof" in out["assessment"]["caveat"]


def test_student_hunt_scopes_and_lens():
    cap = hunt.student_hunt("undergraduate", "mechanical engineering", "capstone", 30, 3, ["assistive devices"])
    assert cap["lens"] == "hardware" and "milestones" in cap["scope_guardrails"][0]
    fair = hunt.student_hunt("high school", "biology", "science_fair", 4)
    assert fair["lens"] == "research" and "adult sign-off" in fair["level_note"] and "hypothesis" in fair["scope_guardrails"][0]
    hack = hunt.student_hunt("undergraduate", "computer science", "hackathon", 0.3)
    assert "3-minute demo" in hack["scope_guardrails"][0] and hack["lens"] == "software"
    assert "feasible for you (30)" in hack["student_rubric"] and "permission" in hack["ethics_note"]


def test_student_domains_are_explorable():
    assert any(d["domain"].startswith("student:") for d in hunt.explore_domains("campus")["domains"])


def test_server_exposes_v4_tools():
    import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"student_hunt", "check_if_solved", "find_research_gaps"} <= names


# ---------------------------------------------------------------- v4.1: fixes found by live testing
from radar import pain  # noqa: E402


def test_relevance_ignores_stopwords_and_requires_all_words_for_short_topics():
    assert pain.content_words("assistive technology for hand mobility") == ["assistive", "technology", "hand", "mobility"]
    off = "Future work on knowledge-defined networking applications for 6G"
    assert not pain.is_relevant("assistive technology for hand mobility", off)      # 'for' no longer counts
    assert not pain.is_relevant("assistive devices", "Wifi disconnection issue on some devices")  # missing 'assistive'
    assert pain.is_relevant("assistive devices", "Audio loops: hearing aids and assistive devices are too expensive")


def test_query_variants_shorten_long_problem_statements():
    v = pain.query_variants("low-cost assistive device for people with limited hand mobility")
    assert v[0] == "low-cost assistive device hand mobility"
    assert "low-cost" in v[1] and len(v[1].split()) >= 3


def test_plan_is_broad_first_not_exact_phrase_only():
    jobs = research.plan("assistive devices", "quick", lens="hardware")
    hn = [j.query for j in jobs if j.source == "hn"]
    assert "assistive devices" in hn and all('"' not in q for q in hn)          # no exact-phrase AND niche in quick runs
    deep = research.plan("assistive devices", "deep", lens="hardware")
    assert any('"' in j.query for j in deep if j.source == "hn")


def test_topic_aware_stack_exchange_sites():
    sites = {j.opts["site"] for j in research.plan("assistive devices", "quick", lens="hardware") if j.source == "se"}
    assert {"ux", "hardwarerecs"} & sites and "superuser" not in sites


def test_hardware_with_no_results_is_inconclusive_not_unsolved(monkeypatch):
    for src in ("github_repo", "scholar", "hn", "reddit"):
        monkeypatch.setitem(S.SOURCES, src, lambda q, limit=15, **k: S.Result([]))
    out = solved.check("low-cost assistive device for limited hand mobility", "hardware")
    a = out["assessment"]
    assert a["hint"] == "inconclusive_products_not_covered" and "retail" in a["caveat"]
    assert out["searched_as"][0] == "low-cost assistive device hand mobility"


def test_plenty_of_irrelevant_results_means_no_clear_solution(monkeypatch):
    junk = [S.Post("hn", f"hn-j{i}", f"Unrelated {i}", "nothing about it", f"https://e.com/{i}", "x", 0, 0, "2026-01-01") for i in range(20)]
    monkeypatch.setitem(S.SOURCES, "hn", lambda q, limit=20, **k: S.Result(list(junk)))
    monkeypatch.setitem(S.SOURCES, "github_repo", lambda q, limit=15, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "scholar", lambda q, limit=15, **k: S.Result([]))
    out = solved.check("quantum widget polisher", "software")
    assert out["assessment"]["hint"] == "no_clear_solution_found"


def test_academic_filler_is_not_a_theme():
    ps = [P("scholar", i, "A study", "This study presents results of a review of the methods and data conducted in background analysis of exoskeleton gloves", "", 1, 0) for i in range(3)]
    terms = {t["term"] for t in research.themes(ps, "exoskeleton gloves")}
    assert not terms & {"study", "results", "methods", "data", "conducted", "review", "analysis", "background"}


# ---------------------------------------------------------------- v4.2: synonyms, near misses, web suggestions
def test_synonyms_via_also_recover_posts_that_use_other_words(monkeypatch):
    wc = S.Post("hn", "hn-w1", "Wheelchair power assist is unaffordable", "frustrating: a wheelchair power assist costs thousands, unaffordable for most users",
                "https://news.ycombinator.com/item?id=1", "u1", 5, 2, "2026-01-01")
    monkeypatch.setitem(S.SOURCES, "hn", lambda q, limit=20, **k: S.Result([wc]))
    monkeypatch.setitem(S.SOURCES, "se", lambda q, limit=20, **k: S.Result([]))
    plain = research.research("assistive devices", lens="hardware", force=True)
    assert plain["posts_relevant"] == 0
    assert any("Wheelchair" in m["title"] for m in plain["near_misses"]) and "also=" in plain["near_misses_note"]
    with_syn = research.research("assistive devices", lens="hardware", also=["wheelchair"], force=True)
    assert with_syn["posts_relevant"] == 1 and with_syn["searched_terms"] == ["assistive devices", "wheelchair"]
    jobs = research.plan("assistive devices", "quick", lens="hardware", also=["wheelchair", "prosthetic"])
    assert any(j.query == "wheelchair" for j in jobs if j.source == "hn")


def test_papers_show_the_sentence_that_states_the_gap(monkeypatch):
    paper = S.Post("scholar", "oa-9", "Hand rehabilitation robots",
                   "Robots help recovery in many clinics. Little is known about home use by older adults. We review devices.",
                   "https://doi.org/10.1/g", "", 12, 0, "2025", {"site": "openalex"})
    monkeypatch.setitem(S.SOURCES, "scholar", lambda q, limit=20, **k: S.Result([paper]))
    out = research.research("hand rehabilitation robots", lens="research", goal="research", force=True)
    item = next(p for p in out["top_posts"] if p["source"].startswith("scholar"))
    assert item["gap_sentence"].startswith("Little is known about home use")


def test_web_search_suggestions_offered_when_no_web_key():
    out = research.research("assistive devices", lens="hardware", force=True)
    assert any("price buy" in q for q in out["llm_web_search_suggestions"])


def test_check_if_solved_suggests_product_searches(monkeypatch):
    for src in ("github_repo", "scholar", "hn", "reddit"):
        monkeypatch.setitem(S.SOURCES, src, lambda q, limit=15, **k: S.Result([]))
    out = solved.check("low-cost assistive device for limited hand mobility", "hardware")
    assert any("buy price" in q for q in out["llm_web_search_suggestions"]) and "web search" in out["web_search_note"]


def test_research_tool_accepts_also():
    import server
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "research_niche")
    assert "also" in tool.inputSchema["properties"]


# ---------------------------------------------------------------- Reddit app login (no username or password)
def test_reddit_uses_app_login_with_user_agent_and_never_a_password(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, auth=None, method="GET", data=None):
        calls.append({"url": url, "headers": headers or {}, "auth": auth, "method": method, "data": data})
        if "access_token" in url:
            return {"access_token": "tok123", "expires_in": 3600}, ""
        return {"data": {"children": [{"data": {"id": "a1", "title": "Need a better grip aid", "selftext": "it is expensive and I struggle",
                                                 "permalink": "/r/x/comments/a1/", "author": "u", "score": 3, "num_comments": 1,
                                                 "created_utc": 1700000000, "subreddit": "x"}}]}}, ""

    monkeypatch.setattr(S, "_get", fake_get)
    monkeypatch.setitem(S._reddit_token, "value", "")
    monkeypatch.setitem(S._reddit_token, "exp", 0.0)
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id123")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret123")
    monkeypatch.setenv("REDDIT_USER_AGENT", "problem-radar/4.2 by u/tester")
    res = S.reddit("grip aid", 5)
    assert res.ok and res.posts[0].title == "Need a better grip aid"
    token_call, search_call = calls
    assert token_call["data"] == {"grant_type": "client_credentials"} and token_call["auth"] == ("id123", "secret123")
    assert "password" not in str(token_call["data"]).lower()
    assert search_call["url"].startswith("https://oauth.reddit.com/") and search_call["headers"]["Authorization"] == "bearer tok123"
    assert search_call["headers"]["User-Agent"] == "problem-radar/4.2 by u/tester"
    assert S.enabled()["reddit"]["note"] == "oauth"


def test_relevance_matches_word_starts_not_substrings():
    from radar.pain import relevance
    assert relevance("hearing aid", "He said the film was gripping") == 0.0 or relevance("hearing aid", "He said the film was gripping") < 1.0
    assert relevance("aid", "he said hello") == 0.0
    assert relevance("grip", "a gripping film") == 0.0
    assert relevance("grip aid", "my grip aid broke") == 1.0
    assert relevance("invoices", "the invoice export is broken") == 1.0
    assert relevance("assistive devices", "Home Assistant dashboard") < 1.0


# ---------------------------------------------------------------- v4.5: community-first Reddit, SE cooldown
def test_find_subreddits_keeps_only_topical_nonadult_communities(monkeypatch):
    kids = [{"data": {"display_name": "HearingAids", "title": "Hearing aids", "public_description": "", "subscribers": 20000}},
            {"data": {"display_name": "Fortnite", "title": "Games", "public_description": "", "subscribers": 900000}},
            {"data": {"display_name": "hearingadult", "title": "hearing", "public_description": "", "subscribers": 5000, "over18": True}},
            {"data": {"display_name": "tinyhearing", "title": "hearing aids", "public_description": "", "subscribers": 20}}]
    monkeypatch.setattr(S, "_reddit_json", lambda path, params: ({"data": {"children": kids}}, ""))
    subs, err = S.find_subreddits("hearing aids")
    assert subs == ["HearingAids"] and not err


def test_reddit_community_reads_top_posts_from_found_subreddits(monkeypatch):
    monkeypatch.setattr(S, "find_subreddits", lambda q, want=3: (["HearingAids"], ""))
    post = S.Post("reddit", "rd-1", "Batteries die constantly", "so annoying and expensive", "https://r/1", "u", 50, 9, "2026-09-01", {"site": "HearingAids"})
    seen = {}

    def fake_reddit(query, limit=20, subreddit=None, sort="relevance", **k):
        seen.update(subreddit=subreddit, sort=sort)
        return S.Result([post])

    monkeypatch.setattr(S, "reddit", fake_reddit)
    res = S.reddit_community("hearing aids")
    assert seen == {"subreddit": "HearingAids", "sort": "top"} and res.posts[0].meta["community"] == "tight"


def test_community_posts_stay_relevant_even_without_the_exact_words():
    p = S.Post("reddit", "rd-2", "Batteries die constantly and it is so annoying", "I hate how expensive these are",
               "https://r/2", "u", 90, 12, "2026-09-02", {"site": "HearingAids", "community": True})
    off = S.Post("reddit", "rd-3", "Batteries die constantly and it is so annoying", "I hate how expensive these are",
                 "https://r/3", "u2", 90, 12, "2026-09-02", {"site": "Fortnite"})
    ranked, _ = research._rank([p, off], ["hearing aids"])
    assert [x[1].id for x in ranked] == ["rd-2"]


def test_se_stops_hammering_after_a_429(monkeypatch):
    calls = []
    monkeypatch.setitem(S._se_cooldown, "until", 0.0)
    monkeypatch.setattr(S, "_get", lambda *a, **k: (calls.append(1), (None, "rate limited (429)"))[1])
    first, second = S.se("x", 5, site="diy"), S.se("y", 5, site="diy")
    assert not first.ok and not second.ok and len(calls) == 1 and "STACKEXCHANGE_KEY" in first.error
    monkeypatch.setitem(S._se_cooldown, "until", 0.0)


def test_fda_devices_turns_adverse_events_into_posts(monkeypatch):
    payload = {"results": [{"mdr_report_key": "123", "date_received": "20240115", "event_type": "Malfunction",
                            "device": [{"generic_name": "wheelchair, powered", "brand_name": "ACME"}],
                            "mdr_text": [{"text_type_code": "Additional Manufacturer Narrative", "text": "Repair done."},
                                         {"text_type_code": "Description of Event or Problem", "text": "THE CHAIR IS NOW BROKEN AND NO LONGER IN USE."}]},
                           {"mdr_report_key": "124", "device": [{}], "mdr_text": []}]}
    monkeypatch.setattr(S, "_get", lambda *a, **k: (payload, ""))
    res = S.fda_devices("wheelchair", 5)
    assert res.ok and len(res.posts) == 1  # the report with no text is dropped
    p = res.posts[0]
    assert p.title.startswith("The chair is now broken") and p.created == "2024-01-15" and "ACME" in p.text and p.source == "fda_devices"


def test_fda_devices_no_match_is_empty_not_failure(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda *a, **k: (None, "HTTPStatusError: Client error '404 NOT FOUND'"))
    res = S.fda_devices("zzzz", 5)
    assert res.ok and res.posts == []


# ---------------------------------------------------------------- v4.7: regions, Europe PMC
def test_region_resolves_names_codes_and_free_text():
    from radar import regions as R
    assert R.resolve("India")["code"] == "IN" and R.resolve("uk")["code"] == "GB" and R.resolve("United Kingdom")["code"] == "GB"
    assert R.resolve("") is None and R.resolve("worldwide") is None
    assert R.resolve("Kerala")["name"] == "Kerala" and R.resolve("Kerala")["code"] == ""


def test_no_region_stays_worldwide_and_region_adds_local_communities():
    worldwide = research.plan("elder care", "quick", lens="policy")
    assert not any(j.opts.get("subreddit") for j in worldwide)
    india = research.plan("elder care", "quick", lens="policy", region=R_.resolve("India"))
    assert any(j.source == "reddit" and j.opts.get("subreddit") == "india" for j in india)
    assert not any(j.source == "reddit_community" and "India" in j.query for j in india)  # the region must not widen community discovery
    assert not any(j.source in ("petitions", "nyc311") for j in india)  # official data is UK and US only
    uk = research.plan("elder care", "quick", lens="policy", region=R_.resolve("UK"))
    assert any(j.source == "petitions" for j in uk) and not any(j.source == "nyc311" for j in uk)


def test_explicit_sources_override_region_filtering():
    jobs = research.plan("elder care", "quick", sources=["petitions"], region=R_.resolve("India"))
    assert any(j.source == "petitions" for j in jobs)


def test_region_result_is_honest_about_missing_official_data():
    out = research.research("elder care", lens="policy", region="India", force=True)
    assert out["region"]["code"] == "IN" and "no official-data connector for India" in out["region_note"]
    assert all("India" in q for q in out["llm_web_search_suggestions"])
    plain = research.research("elder care", lens="policy", force=True)
    assert "region" not in plain


def test_region_changes_the_cache_key(tmp_path):
    research.research("invoices", force=True)
    research.research("invoices", region="India", force=True)
    names = sorted(p.name for p in tmp_path.glob("*.json"))
    assert len(names) == 2 and any("in" in n for n in names)


def test_europepmc_turns_results_into_papers_with_abstracts(monkeypatch):
    payload = {"resultList": {"result": [
        {"id": "123", "source": "MED", "title": "Caregiver burden in dementia", "abstractText": "Little is known about home support. Further research is needed.",
         "pubYear": "2025", "citedByCount": 7, "authorString": "A B"},
        {"id": "9", "source": "MED", "title": "No abstract here"}]}}
    monkeypatch.setattr(S, "_get", lambda *a, **k: (payload, ""))
    res = S.europepmc("dementia caregiver", 5)
    assert len(res.posts) == 1 and res.posts[0].url == "https://europepmc.org/article/MED/123" and res.posts[0].score == 7


def test_loose_community_posts_must_mention_the_topic_but_tight_ones_need_not():
    def post(i, comm, text):
        return S.Post("reddit", f"rd-{i}", text, "this is so annoying and expensive, I hate it", f"https://r/{i}", f"u{i}", 5, 1, "2026-09-01",
                      {"site": "x", "community": comm})
    tight = post(1, "tight", "My airline broke it")
    loose_off = post(2, "loose", "Totally unrelated candle holder story")
    loose_on = post(3, "loose", "Hearing is exhausting")
    ranked, _ = research._rank([tight, loose_off, loose_on], ["hearing aids"])
    assert sorted(x[1].id for x in ranked) == ["rd-1", "rd-3"]


def test_no_single_source_fills_the_list():
    posts = [S.Post("fda_devices", f"f{i}", f"Chair broke number {i} wheelchair failure", "wheelchair broke", f"https://f/{i}", "", 0, 0, "2024-01-01") for i in range(12)]
    posts += [S.Post("reddit", f"r{i}", f"Wheelchair user frustrated {i}", "my wheelchair is broken and I hate it", f"https://r/{i}", f"u{i}", 5, 1, "2026-01-01", {"site": "wheelchairs"}) for i in range(3)]
    ranked, _ = research._rank(posts, ["wheelchair"])
    ordered = research._diversify(ranked, 10)
    head = ordered[:7]  # the capped list; the overflow only pads the end when too few other posts exist
    assert sum(1 for x in head if x[1].source == "fda_devices") == 4 and sum(1 for x in head if x[1].source == "reddit") == 3
    assert len(ordered) == 15


def test_fda_text_is_made_readable():
    assert S._readable("THE CHAIR IS BROKEN. HE FELL") == "The chair is broken. He fell"
    assert S._readable("Already readable text") == "Already readable text"


def test_multiword_topics_must_appear_close_together():
    from radar.pain import relevance, is_relevant
    scattered = "Moved back home, renting from my parents at age 34. My old apartment was cramped, and the dog is old too."
    assert not is_relevant("old age home", scattered)
    assert is_relevant("old age home", "My grandmother moved into an old age home last year and hates it")
    assert relevance("elder care", "She provides care for her elderly parents") == 1.0
    assert relevance("elder care", "Care is hard. " + "word " * 30 + "my elder brother") < 1.0


def test_openalex_api_key_is_sent_in_request(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-test-key")
    calls = {}

    class OpenAlexResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    def fake_request(method, url, **kwargs):
        calls["method"] = method
        calls["url"] = url
        calls.update(kwargs)
        return OpenAlexResponse()

    monkeypatch.setattr(S.httpx, "request", fake_request)
    result = S.scholar("offline android assistant")
    assert result.ok and result.posts == []
    assert calls["url"] == "https://api.openalex.org/works"
    assert calls["params"]["api_key"] == "openalex-test-key"


def test_gitlab_requires_token_and_maps_public_issue(monkeypatch):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    assert S.gitlab("offline android assistant").skipped

    monkeypatch.setenv("GITLAB_TOKEN", "unit-test-token")
    calls = {}

    def fake_get(url, params=None, headers=None, auth=None, method="GET", data=None):
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        return ([{
            "id": 42,
            "title": "Offline Android assistant crashes on low-memory devices",
            "description": "The app crashes when available RAM is low.",
            "web_url": "https://gitlab.com/example/project/-/issues/42",
            "created_at": "2026-10-10T00:00:00Z",
            "author": {"username": "reporter"},
            "upvotes": 4,
            "downvotes": 1,
            "user_notes_count": 6,
            "state": "opened",
        }], "")

    monkeypatch.setattr(S, "_get", fake_get)
    result = S.gitlab("offline android assistant")

    assert result.ok and len(result.posts) == 1
    assert calls["url"] == "https://gitlab.com/api/v4/search"
    assert calls["params"]["scope"] == "issues"
    assert calls["headers"]["PRIVATE-TOKEN"] == "unit-test-token"
    assert result.posts[0].score == 3
    assert result.posts[0].comments == 6
    assert result.posts[0].meta["site"] == "example/project"
    assert result.posts[0].url.endswith("/-/issues/42")


def test_reddit_oauth_handshake_counts_against_the_two_request_budget(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setitem(S._reddit_token, "value", "")
    monkeypatch.setitem(S._reddit_token, "exp", 0.0)
    jobs = [
        research.Job("reddit_community", "elder care"),
        research.Job("reddit", "elder care"),
    ]

    selected = research._limit_jobs(jobs)
    assert [job.source for job in selected] == ["reddit"]
    assert S.startup_request_cost("reddit") + sum(
        research.SOURCE_REQUEST_COST.get(job.source, 1) for job in selected
    ) == 2

    monkeypatch.setitem(S._reddit_token, "value", "cached-token")
    monkeypatch.setitem(S._reddit_token, "exp", time.time() + 1800)
    selected = research._limit_jobs(jobs)
    # Even on a warm token, direct search gets priority; community discovery would
    # consume both request units and displace the complaint search.
    assert [job.source for job in selected] == ["reddit"]
    assert sum(research.SOURCE_REQUEST_COST.get(job.source, 1) for job in selected) == 1


def test_gitlab_is_excluded_from_default_search_without_token(monkeypatch):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    assert "gitlab" not in {job.source for job in research.plan("offline android assistant", lens="software")}

    monkeypatch.setenv("GITLAB_TOKEN", "unit-test-token")
    assert "gitlab" in {job.source for job in research.plan("offline android assistant", lens="software")}


def test_bluesky_search_uses_public_api_and_maps_posts(monkeypatch):
    calls = {}

    def fake_get(url, params=None, headers=None, auth=None, method="GET", data=None):
        calls["url"] = url
        calls["params"] = params
        return ({"posts": [{
            "uri": "at://did:plc:test/app.bsky.feed.post/abc123",
            "indexedAt": "2026-10-20T12:00:00Z",
            "record": {"text": "I hate how expensive assistive tools are", "createdAt": "2026-10-20T11:00:00Z"},
            "author": {"handle": "user.example"},
            "likeCount": 7,
            "replyCount": 3,
            "repostCount": 2,
        }]}, "")

    monkeypatch.setattr(S, "_get", fake_get)
    result = S.bluesky("assistive tools", limit=100)

    assert result.ok and len(result.posts) == 1
    assert calls["url"] == "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
    assert calls["params"]["limit"] == 25
    assert result.posts[0].source == "bluesky"
    assert result.posts[0].url == "https://bsky.app/profile/user.example/post/abc123"
    assert result.posts[0].score == 7 and result.posts[0].comments == 3


def test_arxiv_parses_atom_feed_and_uses_one_request(monkeypatch):
    monkeypatch.setattr(S, "_arxiv_last_request", 0.0)
    calls = []

    class ArxivResponse:
        status_code = 200
        text = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2601.12345v1</id>
            <title>Offline Assistants for Small Devices</title>
            <summary>We study local assistants for phones without reliable internet access.</summary>
            <published>2026-01-10T00:00:00Z</published>
            <author><name>Researcher One</name></author>
          </entry>
        </feed>'''

    def fake_get(url, params=None, **kwargs):
        calls.append((url, params, kwargs))
        return ArxivResponse()

    monkeypatch.setattr(S.httpx, "get", fake_get)
    result = S.arxiv("offline AI assistant", limit=100)

    assert result.ok and len(result.posts) == 1
    assert len(calls) == 1
    assert calls[0][0] == "https://export.arxiv.org/api/query"
    assert calls[0][1]["max_results"] == 20
    assert result.posts[0].source == "arxiv"
    assert result.posts[0].url == "https://arxiv.org/abs/2601.12345v1"
    assert "without reliable internet" in result.posts[0].text


def test_arxiv_does_not_retry_rate_limit(monkeypatch):
    monkeypatch.setattr(S, "_arxiv_last_request", 0.0)
    calls = []

    class Limited:
        status_code = 429
        text = "Rate exceeded"

    def fake_get(*args, **kwargs):
        calls.append(1)
        return Limited()

    monkeypatch.setattr(S.httpx, "get", fake_get)
    result = S.arxiv("local AI")

    assert not result.ok and "no retry" in result.error
    assert len(calls) == 1


def test_a_passing_mention_does_not_make_a_post_about_the_topic():
    from radar.pain import is_focused
    politics = ("I don't think people realize how dangerous he is. " + "filler words about the election and Ohio politics " * 12
                + "Before politics he ran Axovant, a dementia drug company. " + "more about the polls " * 5)
    assert not is_focused(["dementia"], "I don't think people realize how dangerous he is", politics)
    assert is_focused(["dementia"], "Dementia care is hard", "x")                    # in the title
    assert is_focused(["dementia"], "Help", "My mother has dementia and we cannot cope. " + "word " * 100)  # opening lines
    assert is_focused(["dementia"], "Help", "word " * 100 + "dementia is hard " + "word " * 10 + "dementia again")  # twice


def test_ranking_drops_posts_that_only_mention_the_topic_in_passing():
    off = S.Post("hn", "hn-off", "Why the election matters", "frustrating politics, so expensive. " * 12 + "He once ran a dementia drug company. " + "more politics " * 30,
                 "https://hn/off", "u1", 5, 1, "2026-01-01")
    on = S.Post("hn", "hn-on", "Caring for a parent with dementia", "so frustrating and expensive, I wish there was a better way", "https://hn/on", "u2", 5, 1, "2026-01-01")
    ranked, _ = research._rank([off, on], ["dementia"])
    assert [x[1].id for x in ranked] == ["hn-on"]


def test_output_hides_usernames_and_labels_evidence_and_age():
    out = research.research("accounting invoices", force=True)
    assert out["top_posts"] and all("author" not in p for p in out["top_posts"])
    assert all(p["evidence_type"] in ("reported_need", "measured_outcome", "service_request", "research_gap", "web_lead") for p in out["top_posts"])
    assert all("age_years" in p for p in out["top_posts"]) and "not a survey" in out["evidence_note"].lower()


def test_old_posts_are_not_filtered_out(monkeypatch):
    seen = {}

    def fake(url, params=None, headers=None, **k):
        seen.update(params or {})
        return {"hits": []}, ""

    monkeypatch.setattr(S, "_get", fake)
    S.hn("wheelchair")
    assert "numericFilters" not in seen
    calls = {}
    monkeypatch.setattr(S, "_reddit_json", lambda path, params: (calls.update(params) or {"data": {"children": []}}, ""))
    monkeypatch.setattr(S, "_get", lambda *a, **k: (calls.update(a[1] or {}) or {"data": {"children": []}}, ""))
    S.reddit("wheelchair")
    assert calls.get("t") == "all"


# Regression tests for the October 2026 audit.
def test_blank_queries_are_rejected_before_any_source_request(monkeypatch):
    from radar import solved

    def forbidden(*args, **kwargs):
        pytest.fail("blank input must be rejected before searching")

    monkeypatch.setattr(research, "run_jobs", forbidden)
    monkeypatch.setattr(solved, "run_jobs", forbidden)
    with pytest.raises(ValueError):
        research.research(" ")
    with pytest.raises(ValueError):
        research.search("")
    with pytest.raises(ValueError):
        research.validate("\t")
    with pytest.raises(ValueError):
        solved.check("  ")


def test_blank_topic_is_never_perfectly_relevant():
    from radar import pain

    assert pain.relevance("", "unrelated gaming discussion") == 0.0
    assert not pain.is_relevant("", "unrelated gaming discussion")


def test_cache_does_not_mix_topics_with_the_same_slug():
    first = research.research("quickbooks/invoices", force=True)
    second = research.research("quickbooks invoices")
    assert first["niche"] == "quickbooks/invoices"
    assert second["niche"] == "quickbooks invoices"
    assert not second["from_cache"]


def test_nyc_is_a_distinct_region_and_keeps_national_fda_data():
    from radar import regions

    nyc = regions.resolve("New York City")
    assert nyc["code"] == "NYC"
    assert regions.applies("nyc311", nyc)
    assert regions.applies("fda_devices", nyc)
    assert not regions.applies("nyc311", regions.resolve("United States"))


def test_unrelated_post_from_topic_community_is_rejected():
    post = P("reddit", 999, "Android game battery discussion",
             "The game crashes and is frustrating to play.", "player", community="tight")
    ranked, _ = research._rank([post], ["offline AI assistant for low-end Android phones"])
    assert not ranked


def test_unrelated_purchase_is_not_a_paying_signal(monkeypatch):
    post = P("hn", 998, "Quickbooks invoices reconciliation is frustrating",
             "I am tired of this. Separately, I paid $500 for a new laptop.", "writer")
    monkeypatch.setattr(research, "run_jobs", lambda jobs: ([post], {}))
    out = research.validate("quickbooks invoices reconciliation", "accounting")
    assert out["counts"]["paying_signals"] == 0


def test_hunt_plan_keeps_a_specific_unmapped_interest():
    from radar import hunt

    interest = "offline AI assistant for low-end Android phones"
    result = hunt.plan_hunt(interests=[interest], skills=["python"], lens="software")
    assert result["seed_niches"][0]["niche"] == interest


def test_student_hunt_keeps_a_specific_project_interest():
    from radar import hunt

    interest = "offline AI assistant for low-end Android phones"
    result = hunt.student_hunt(field="computer science", interests=[interest])
    assert result["seed_niches"][0]["niche"] == interest



def test_timed_out_source_job_keeps_its_global_capacity_slot(monkeypatch):
    import threading
    from threading import BoundedSemaphore

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(research, "_SOURCE_SLOTS", slots)
    monkeypatch.setattr(research, "DEADLINE", 0.01)

    def blocked_source(query, limit=20, **kwargs):
        started.set()
        try:
            release.wait(timeout=2)
            return S.Result([])
        finally:
            finished.set()

    monkeypatch.setitem(S.SOURCES, "hn", blocked_source)
    try:
        _, first = research.run_jobs([research.Job("hn", "first")])
        assert started.wait(timeout=1)
        assert first["hn"]["errors"] == ["timed out"]
        assert first["hn"]["timed_out"] == 1

        _, second = research.run_jobs([research.Job("hn", "second")])
        assert second["hn"]["capacity_limited"] is True
        assert second["hn"]["state"] == "skipped"
    finally:
        release.set()
        # Ensure the worker and its done callback finish before restoring the semaphore.
        assert finished.wait(timeout=1)
        deadline = time.monotonic() + 1
        acquired = False
        while time.monotonic() < deadline:
            if slots.acquire(blocking=False):
                slots.release()
                acquired = True
                break
            time.sleep(0.01)
        assert acquired

def test_personal_json_tools_refuse_network_transport():
    env = os.environ.copy()
    env["ENABLE_PERSONAL"] = "1"
    env["TRANSPORT"] = "streamable-http"
    result = subprocess.run(
        [sys.executable, "-c", "import server"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "local stdio use only" in result.stderr


# Constraint-aware retrieval and public free-tier budget regressions.
def test_query_variants_preserve_offline_low_resource_and_platform_constraints():
    phrase = "Students with low-end Android phones need an AI assistant that works offline because mobile data is unreliable"
    variants = pain.query_variants(phrase)
    assert len(variants) >= 1
    for term in ("offline", "low-end", "android"):
        assert term in variants[0].lower()
        assert all(term in variant.lower() for variant in variants)


def test_ranking_requires_explicit_hard_constraints_even_with_topic_overlap():
    niche = "offline AI assistant for low-end Android phones"
    valid = P("hn", 1201, "Offline AI assistant for low-end Android phones",
              "This runs offline on low-end Android phones with limited RAM; it is frustrating and I wish there were a better way.", "a")
    misses_resource = P("hn", 1202, "Offline AI assistant for Android",
                        "This is frustrating; I have to manually configure it. The assistant runs offline on Android but needs a flagship phone with 12 GB RAM.", "b")
    ranked, near = research._rank([valid, misses_resource], [niche])
    assert [item[1].id for item in ranked] == ["hn-1201"]
    assert any(item[1].id == "hn-1202" for item in near)
    assert "low-resource hardware" in pain.missing_constraints(niche, misses_resource.title + " " + misses_resource.text)


def test_validation_does_not_attach_payment_or_workaround_to_an_unrelated_sentence(monkeypatch):
    p = P("hn", 1203, "Quickbooks invoices are frustrating",
          "I paid $500 for a laptop. For rent, I use a spreadsheet and copy paste the numbers.", "a")
    monkeypatch.setattr(research, "run_jobs", lambda jobs: ([p], {"hn": {"state": "ok", "posts": 1}}))
    out = research.validate("quickbooks invoices reconciliation", "accounting")
    assert out["counts"]["paying_signals"] == 0
    assert out["counts"]["willingness_to_pay_signals"] == 0
    assert out["counts"]["workaround_signals"] == 0
    assert out["evidence_status"] == "insufficient_evidence"
    assert "does not prove" in out["evidence_note"]


def test_validation_does_not_count_vendor_editorial_as_market_demand(monkeypatch):
    vendor_article = P(
        "reddit", "vendor-ap-automation",
        "How Healthcare Teams Can Use AP Automation Software",
        "The hidden cost of manual AP in healthcare is large. "
        "Our manual invoice reconciliation software costs $50 per month, and teams can use a spreadsheet workaround.",
        "vendor-account",
    )
    monkeypatch.setattr(
        research, "run_jobs",
        lambda jobs: ([vendor_article], {"reddit": {"state": "ok", "posts": 1}, "hn": {"state": "ok", "posts": 0}}),
    )

    out = research.validate("manual invoice reconciliation", "accounting invoice reconciliation")

    assert out["counts"]["paying_signals"] == 0
    assert out["counts"]["willingness_to_pay_signals"] == 0
    assert out["counts"]["workaround_signals"] == 0
    assert out["evidence_status"] == "insufficient_evidence"


def test_validation_separates_existing_spend_from_explicit_willingness_to_pay(monkeypatch):
    p = P("hn", 1204, "Offline AI assistant for low-end Android phones",
          "I would pay $5 a month for an offline AI assistant on a low-end Android phone.", "a")
    monkeypatch.setattr(research, "run_jobs", lambda jobs: ([p], {"hn": {"state": "ok", "posts": 1}, "reddit": {"state": "ok", "posts": 0}}))
    out = research.validate("offline AI assistant for low-end Android phones", "offline Android AI")
    assert out["counts"]["paying_signals"] == 0
    assert out["counts"]["willingness_to_pay_signals"] == 1
    assert out["required_constraints"] == ["offline operation", "low-resource hardware", "Android platform"]


def test_public_request_job_budget_is_bounded_and_source_diverse(monkeypatch):
    calls = []
    for source in ("hn", "reddit", "se"):
        def fake(query, limit=20, _source=source, **kwargs):
            calls.append((_source, query))
            return S.Result([])
        monkeypatch.setitem(S.SOURCES, source, fake)
    jobs = [research.Job(source, f"{source}-{i}") for i in range(10) for source in ("hn", "reddit", "se")]
    _, status = research.run_jobs(jobs)
    assert len(calls) <= research.MAX_JOBS_PER_REQUEST
    assert all(status[source]["request_limited"] for source in ("hn", "reddit", "se"))
    assert all(status[source]["state"] == "partial" for source in ("hn", "reddit", "se"))
    assert len({source for source, _ in calls}) == 3


def test_query_length_is_bounded_before_source_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("oversized query must be rejected before searching")
    monkeypatch.setattr(research, "run_jobs", forbidden)
    with pytest.raises(ValueError, match="400 characters"):
        research.research("a" * 401)
    with pytest.raises(ValueError, match="400 characters"):
        research.search("a" * 401)
    with pytest.raises(ValueError, match="400 characters"):
        research.validate("a" * 401)


def test_constraint_match_rejects_explicit_contradictions():
    niche = "offline AI assistant for low-end Android phones"
    assert not pain.constraints_match(niche, "Android assistant, but cloud-only and requires an internet connection")
    assert not pain.constraints_match("local AI assistant for Android", "This is not local AI; all inference runs on a cloud server.")
    assert not pain.constraints_match(niche, "Offline Android assistant that requires at least 12 GB RAM")
    assert not pain.constraints_match("free Android assistant", "Android assistant; subscription required and not free")
    assert pain.constraints_match(niche, "Fully local inference runs offline on low-end Android phones with 4 GB RAM")


def test_denied_android_support_does_not_satisfy_platform_constraint():
    assert "Android platform" in pain.missing_constraints(
        "Android app for offline note-taking",
        "This app is not supported on Android; use the iOS version instead."
    )


def test_source_selection_lists_are_bounded_and_deduplicated(monkeypatch):
    with pytest.raises(ValueError, match="at most 12 items"):
        research.plan("offline android assistant", sources=["hn"] * 13)
    with pytest.raises(ValueError, match="at most 12 items"):
        research.plan("offline android assistant", se_sites=["android"] * 13)

    hn_jobs = [j for j in research.plan("accounting", sources=["hn", "hn"]) if j.source == "hn"]
    assert len(hn_jobs) == len(research.plan("accounting", sources=["hn"]))

    def forbidden(*args, **kwargs):
        pytest.fail("source list size must be validated before source work")
    monkeypatch.setattr(research, "run_jobs", forbidden)
    with pytest.raises(ValueError, match="at most 12 items"):
        research.search("offline android", sources=["hn"] * 13)


def test_validation_does_not_count_negated_payment_as_spend_or_intent(monkeypatch):
    p = P("hn", 1210, "Offline AI assistant for low-end Android phones",
          "I did not pay for the offline AI assistant on my low-end Android phone. It is frustrating and I wish it worked better.", "a")
    monkeypatch.setattr(research, "run_jobs", lambda jobs: ([p], {"hn": {"state": "ok", "posts": 1}}))
    out = research.validate("offline AI assistant for low-end Android phones", "offline Android AI")
    assert out["counts"]["paying_signals"] == 0
    assert out["counts"]["willingness_to_pay_signals"] == 0


def test_research_reports_planned_completed_and_succeeded_jobs_separately():
    out = research.research("accounting invoices", force=True)
    assert out["queries_planned"] >= out["queries_run"] >= out["queries_succeeded"]
    assert "queries_timed_out" in out
    assert "queries_cancelled_before_start" in out


# Regression: provider request caps are enforced without a fallback phase.
def test_research_obeys_provider_and_global_request_budgets_without_fallback(monkeypatch):
    calls = []

    def fake_source(source):
        def run(query, limit=20, **kwargs):
            calls.append((source, query))
            return S.Result([])
        return run

    sources = ("reddit_community", "reddit", "github", "github_repo", "gitlab", "hn", "se", "bluesky", "arxiv")
    monkeypatch.setattr(research, "plan", lambda *args, **kwargs: [
        research.Job(source, f"{source}-{i}") for i in range(10) for source in sources
    ])
    for source in sources:
        monkeypatch.setitem(S.SOURCES, source, fake_source(source))

    out = research.research("offline assistant", force=True)

    assert len(calls) <= research.MAX_JOBS_PER_REQUEST
    provider_units = {}
    for source, _ in calls:
        provider = research.SOURCE_PROVIDER_GROUP.get(source, source)
        provider_units[provider] = provider_units.get(provider, 0) + research.SOURCE_REQUEST_COST.get(source, 1)
    assert all(units <= research.MAX_REQUESTS_PER_PROVIDER_PER_CALL for units in provider_units.values())
    assert out["queries_planned"] > out["queries_budgeted"]
    assert out["queries_budgeted"] <= research.MAX_JOBS_PER_REQUEST
    assert out["provider_request_units_budgeted"] <= (
        len(research.SOURCE_PROVIDER_GROUP) + len(S.SOURCES)
    ) * research.MAX_REQUESTS_PER_PROVIDER_PER_CALL
    assert out["queries_run"] <= research.MAX_JOBS_PER_REQUEST
    assert "fallback_note" not in out
    assert "ddg" not in out["coverage"] and "tavily" not in out["coverage"]


def test_validation_applies_hard_constraints_to_document_not_every_sentence(monkeypatch):
    post = P(
        "hn", 1291, "Offline AI assistant for Android",
        "The assistant runs on low-end Android phones with limited RAM and works without internet. "
        "I would pay $5 a month for an assistant that answers questions and keeps notes.",
        "person-a",
    )
    monkeypatch.setattr(
        research, "run_jobs",
        lambda jobs: ([post], {"hn": {"state": "ok", "posts": 1}, "reddit": {"state": "ok", "posts": 0}}),
    )

    out = research.validate("offline AI assistant for low-end Android phones", "offline Android AI")

    assert out["counts"]["willingness_to_pay_signals"] == 1
    assert out["counts"]["paying_signals"] == 0


def test_related_paper_alone_does_not_mean_partially_solved():
    paper = {"name": "Low-Internet Optimized Web Applications for Rural India", "score": 3}

    assessment = solved.assess(
        projects=[], papers=[paper], actions=[], lens="software",
        discussion=[], raw_count=60, sources_ok=3,
    )

    assert assessment["hint"] == "no_clear_solution_found"
    assert any("do not by themselves demonstrate a working solution" in reason for reason in assessment["reasons"])


def test_default_research_prefers_direct_reddit_and_community_is_opt_in():
    niche = "offline AI assistant for low-end Android phones"
    jobs = research.plan(niche, "quick", lens="software")
    assert "reddit" in {j.source for j in jobs}
    assert "reddit_community" not in {j.source for j in jobs}

    explicit = research.plan(niche, "quick", sources=["reddit_community"])
    community = [j for j in explicit if j.source == "reddit_community"]
    assert len(community) == 1
    assert community[0].query == pain.query_variants(niche)[0]


def test_default_planner_skips_bluesky_and_prioritizes_alternate_queries(monkeypatch):
    monkeypatch.setattr(S, "startup_request_cost", lambda provider: 0)
    jobs = research.plan(
        "offline AI assistant for low-end Android phones",
        "quick",
        lens="software",
        also=["on-device LLM", "local AI inference"],
    )
    assert "bluesky" not in {j.source for j in jobs}
    hn_queries = [j.query for j in jobs if j.source == "hn"]
    assert hn_queries[0] == pain.query_variants("offline AI assistant for low-end Android phones")[0]
    assert hn_queries[1] in pain.query_expansions("offline AI assistant for low-end Android phones")
    # Caller-provided alternates are still retained in the plan, but constraint-preserving
    # variants get first priority and the alternate phrases are distributed across sources.
    assert any(j.query == "on-device LLM" for j in jobs)
    assert "bluesky" in {j.source for j in research.plan("offline LLM", "quick", sources=["bluesky"])}


def test_reddit_community_adapter_is_skipped_when_oauth_cold_start_exceeds_cap(monkeypatch):
    monkeypatch.setattr(S, "startup_request_cost", lambda provider: 1 if provider == "reddit" else 0)
    jobs = research.plan("offline LLM", "quick", lens="software")
    assert "reddit_community" not in {j.source for j in jobs}
    assert "reddit" in {j.source for j in jobs}


def test_cross_source_duplicate_titles_are_collapsed_deterministically():
    short = P("reddit", 10, "Running a 270M LLM on Android", "Short copy", "author", score=1, comments=0)
    rich = P("hn", 11, "Running a 270M LLM on Android", "A longer detailed discussion about small language models on low-end Android phones.", "author2", score=2, comments=5)
    duplicate = P("reddit", 12, "Running a 270M LLM on Android", "Another repost", "author3", score=10, comments=10)
    result = research._dedupe([short, rich, duplicate])
    assert len(result) == 1
    assert result[0].source == "hn"


def test_partial_topic_match_is_available_for_lead_triage_but_not_strict_match():
    query = "offline AI assistant for low-end Android phones"
    related = (
        "My small language model runs offline on Android phones, but it keeps crashing "
        "when memory fills. This is frustrating; I have to close other apps to free RAM."
    )
    assert not pain.topic_fit(query, related, "Small language model keeps crashing on Android")
    assert pain.topic_candidate_fit(query, related, "Small language model keeps crashing on Android")
    assert "assistant" in pain.topic_anchor_gaps(query, related, "Small language model keeps crashing on Android")

    unrelated = "A local project on Android runs well and has a simple user interface."
    assert not pain.topic_candidate_fit(query, unrelated, "Android project")


def test_topic_fit_rejects_generic_overlap_and_accepts_domain_aliases():
    unrelated = "I'm forking Ladybird and stepping down as SerenityOS BDFL. A local project is running."
    related = "A 270M language model runs entirely on a budget Android device."
    assert not pain.topic_fit("Android app for running local LLMs", unrelated)
    assert pain.topic_fit("Android app for running local LLMs", related)
    assert pain.topic_fit("offline AI assistant for low-end Android phones", "offline voice chat runs local AI on an Android phone")
    assert not pain.topic_fit("manual invoice reconciliation", "An unrelated project is running on a local server.")


def test_technical_failure_language_counts_as_pain():
    assert pain.looks_like_pain("The Android app keeps crashing with an out of memory (OOM) error.")


def test_solution_check_returns_partial_topic_candidates_without_calling_them_solutions(monkeypatch):
    candidate = S.Post(
        "github_repo", "partial-topic-project", "Small Language Model on Android",
        "A small language model can run offline on Android phones. Some users report crashes "
        "on older devices when memory is exhausted.",
        "https://github.com/example/offline-llm-android", "example", 12, 3, "2026-10-01",
        {"site": "Python", "archived": False},
    )
    monkeypatch.setattr(
        solved, "run_jobs",
        lambda jobs: ([candidate], {"github_repo": {"state": "ok", "posts": 1}}),
    )
    out = solved.check("offline AI assistant for low-end Android phones", "software")

    assert out["existing_projects"] == []
    assert out["related_candidate_count"] == 1
    lead = out["related_candidates"][0]
    assert lead["url"] == candidate.url
    assert lead["candidate_kind"] == "existing_project_candidate"
    assert "assistant" in lead["missing_topic_anchors"]
    assert out["assessment"]["hint"] != "partially_solved"


def test_solution_check_exposes_constraint_near_misses_and_drops_generic_overlap(monkeypatch):
    relevant_near = S.Post(
        "hn", "hn-near", "Offline AI voice chat app for Android",
        "An offline voice chat app runs local AI on Android phones, but it requires a newer device.",
        "https://news.ycombinator.com/item?id=99001", "user", 3, 2, "2026-06-01",
    )
    unrelated = S.Post(
        "hn", "hn-unrelated", "I'm forking Ladybird and stepping down as SerenityOS BDFL",
        "A local project is running and a product discussion is ongoing.",
        "https://news.ycombinator.com/item?id=99002", "user2", 5, 1, "2026-06-02",
    )
    monkeypatch.setitem(S.SOURCES, "hn", lambda q, limit=20, **k: S.Result([relevant_near, unrelated]))
    monkeypatch.setitem(S.SOURCES, "github_repo", lambda q, limit=15, **k: S.Result([]))
    monkeypatch.setitem(S.SOURCES, "scholar", lambda q, limit=15, **k: S.Result([]))
    out = solved.check("offline AI assistant for low-end Android phones", "software")
    titles = [p["title"] for p in out["constraint_near_misses"]]
    assert any("Offline AI voice chat" in title for title in titles)
    assert all("Ladybird" not in title for title in titles)
    assert any("low-resource hardware" in p["missing_constraints"] for p in out["constraint_near_misses"])


def test_partial_topic_matches_are_near_misses_not_top_complaints():
    related = S.Post(
        "hn", "partial-model-anchor", "Small language model keeps crashing on Android",
        "My small language model runs offline on Android phones, but it keeps crashing "
        "when memory fills. This is frustrating; I have to close other apps to free RAM.",
        "https://news.ycombinator.com/item?id=99003", "user", 3, 4, "2026-10-24",
    )
    ranked, misses = research._rank([related], ["offline AI assistant for low-end Android phones"])
    assert ranked == []
    assert any(p.id == "partial-model-anchor" for _, p, _, _ in misses)


def test_promotional_launches_are_near_misses_not_pain_results():
    promo = S.Post(
        "reddit", "promo-launch", "Big Milestone: new Android local LLM app is live",
        "Excited to announce this new Android app for local LLM users. It is now live to download. "
        "Download directly from the App Store today.",
        "https://example.com/promo", "maker", 40, 20, "2026-10-24",
    )
    complaint = S.Post(
        "reddit", "real-crash", "Android local LLM keeps crashing with OOM",
        "My Android phone's local LLM keeps crashing with an out-of-memory error. "
        "It freezes after a prompt and it is frustrating to close other apps to free RAM.",
        "https://example.com/complaint", "user", 3, 9, "2026-10-24",
    )
    ranked, misses = research._rank([promo, complaint], ["Android local LLM"])
    assert [item[1].id for item in ranked] == ["real-crash"]
    assert any(item[1].id == "promo-launch" for item in misses)


def test_long_specific_query_requires_more_topic_anchors():
    assert not pain.topic_fit(
        "Android local LLM crashes out of memory",
        "A local LLM service for Android devices includes memory controls.",
    )
    assert pain.topic_fit(
        "Android local LLM crashes out of memory",
        "The Android app running a local LLM crashes with an out of memory error.",
    )


def test_search_pain_filters_promotions_and_money_only_posts(monkeypatch):
    complaint = S.Post(
        "github", "android-oom", "Android local LLM crashes with memory errors",
        "The Android app running a local LLM crashes under memory pressure after longer prompts; "
        "this is frustrating when it stops responding.",
        "https://example.com/oom", "reporter", 1, 4, "2026-10-24",
    )
    promotional = S.Post(
        "reddit", "launch-local-ai", "Offline Android local LLM app is now live",
        "Excited to announce a new offline Android local LLM app. It is now live and available to download. "
        "Download directly from the App Store today.",
        "https://example.com/launch", "maker", 50, 30, "2026-10-24",
    )
    money_only = S.Post(
        "reddit", "mac-price", "Local LLM Mac setup cost",
        "I pay $20 per month for a subscription and use a Mac for local inference.",
        "https://example.com/cost", "user", 5, 9, "2026-10-24",
    )
    monkeypatch.setitem(S.SOURCES, "github", lambda q, limit=20, **k: S.Result([complaint]))
    monkeypatch.setitem(S.SOURCES, "reddit", lambda q, limit=20, **k: S.Result([promotional, money_only]))
    monkeypatch.setitem(S.SOURCES, "hn", lambda q, limit=20, **k: S.Result([]))

    out = research.search(
        "offline Android local LLM crashes out of memory",
        sources=["github", "reddit", "hn"],
    )
    assert [p["url"] for p in out["results"]] == ["https://example.com/oom"]
    assert "offline operation" in out["results"][0]["missing_constraints"]
    assert "missing_constraints" in out["results"][0]
