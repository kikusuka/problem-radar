import pytest

from radar import research, verify
from radar import sources as S


@pytest.fixture(autouse=True)
def clean_index():
    verify._index.clear()
    yield
    verify._index.clear()


def seed():
    verify.remember("https://example.com/a", "Crop insurance claims are delayed",
                    "Farmers in Punjab say crop insurance claims take 6 months to pay out. About 40% never got paid.")


def test_supported_claim_shows_the_sentence():
    seed()
    out = verify.check_claims([{"claim": "Crop insurance claims take 6 months to pay out in Punjab", "urls": ["https://example.com/a"]}])
    c = out["claims"][0]
    assert c["status"] == "supported_by_text" and "6 months" in c["citations"][0]["best_sentence"]


def test_invented_url_is_flagged():
    seed()
    c = verify.check_claims([{"claim": "Claims take 6 months", "urls": ["https://example.com/never-returned"]}])["claims"][0]
    assert c["status"] == "url_not_retrieved"


def test_invented_number_is_flagged():
    seed()
    c = verify.check_claims([{"claim": "Crop insurance claims in Punjab take 9 months to pay out", "urls": ["https://example.com/a"]}])["claims"][0]
    assert c["status"] != "supported_by_text" and c["citations"][0]["numbers_not_in_source"] == ["9"]


def test_unrelated_claim_is_not_found():
    seed()
    c = verify.check_claims([{"claim": "Electric tractors are cheaper than diesel tractors", "urls": ["https://example.com/a"]}])["claims"][0]
    assert c["status"] == "not_found_in_text"


def test_claim_without_citation_and_bad_input():
    assert verify.check_claims([{"claim": "Something is true"}])["claims"][0]["status"] == "no_citation"
    with pytest.raises(ValueError):
        verify.check_claims([])
    with pytest.raises(ValueError):
        verify.check_claims([{"claim": "x", "urls": "not-a-list"}])


def test_read_thread_text_is_registered(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda *a, **k: ({"title": "T", "text": "", "children": [{"text": "I pay 30 dollars a month", "children": []}]}, ""))
    research.read_thread("https://news.ycombinator.com/item?id=7")
    row = verify._index[verify._norm("https://news.ycombinator.com/item?id=7")]
    assert "30 dollars" in row["text"]


def test_number_words_match_digits():
    verify.remember("https://example.com/n", "Delays", "Claims take six months to pay out for farmers in the district.")
    c = verify.check_claims([{"claim": "Claims take 6 months to pay out for farmers in the district", "urls": ["https://example.com/n"]}])["claims"][0]
    assert c["status"] == "supported_by_text"
