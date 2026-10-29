from radar import library


def test_library_loads_all_entries_with_provenance():
    out = library.find("")
    assert out["libraries"]["sih2025"]["entries"] == 100
    assert out["libraries"]["nasa2025"]["entries"] == 18
    assert all(m["url"].startswith("https://") and m["event"] and m["year"] == 2025 for m in out["matches"])


def test_topic_search_finds_relevant_and_excludes_unrelated():
    titles = [m["title"].lower() for m in library.find("groundwater")["matches"]]
    assert titles and all("groundwater" in t or "water" in t for t in titles)
    assert library.find("zzzxqq")["matches"] == []


def test_plural_and_kind_filter():
    crops = library.find("crops advisory")["matches"]
    assert any("Crop Advisory" in m["title"] for m in crops)
    assert all(m.get("kind", "hardware") == "hardware" for m in library.find("farm", kind="hardware")["matches"])


def test_output_says_it_is_not_demand_evidence():
    assert "not evidence" in library.find("water")["how_to_read"]
