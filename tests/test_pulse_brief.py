import json
import time

import pytest

from radar import brief, pulse, verify
from radar import sources as S


@pytest.fixture
def feed(monkeypatch, tmp_path):
    monkeypatch.setattr(pulse, "PULSE_FILE", tmp_path / "pulse.json")
    pulse._mem.update(at=0.0, data=None)

    def fake_get(url, params=None, **k):
        if "algolia" in url:
            return {"hits": [
                {"title": "Ask HN: How do you handle late client payments? I'm struggling", "story_text": "I keep chasing invoices by hand, it wastes hours", "objectID": "1",
                 "num_comments": 12, "created_at": "2026-10-20T10:00:00Z"},
                {"title": "Ask HN: What is your favourite keyboard?", "story_text": "just curious", "objectID": "2", "num_comments": 9, "created_at": "2026-10-21T10:00:00Z"},
            ]}, ""
        return {"data": [{"id": 5, "attributes": {"action": "Fund hospice care at home", "signature_count": 5000, "created_at": "2026-09-01T00:00:00Z", "background": "care"}},
                         {"id": 6, "attributes": {"action": "Ban pineapple pizza", "signature_count": 90000, "created_at": "2026-09-02T00:00:00Z", "background": ""}}]}, ""
    monkeypatch.setattr(S, "_get", fake_get)


def test_pulse_keeps_problem_asks_and_labels_the_sample(feed):
    out = pulse.find("")
    titles = [i["title"] for i in out["matches"]]
    assert any("late client payments" in t for t in titles)
    assert not any("keyboard" in t for t in titles)
    assert out["from"] == "live_build" and "not a census" in out["what_this_is"]


def test_pulse_topic_filter_and_saved_file_is_used_when_fresh(feed):
    pulse.save()
    out = pulse.find("late payments")
    assert out["from"] == "saved_file" and out["total_matches"] >= 1
    assert all("pizza" not in i["title"] for i in out["matches"])


def test_pulse_stale_file_triggers_live_build(feed):
    data = pulse.build()
    data["generated_at"] = int(time.time()) - 10 * 86400
    pulse.PULSE_FILE.write_text(json.dumps(data))
    assert pulse.find("")["from"] == "live_build"


def test_pulse_reports_failed_source_instead_of_hiding_it(monkeypatch, tmp_path):
    monkeypatch.setattr(pulse, "PULSE_FILE", tmp_path / "p.json")
    pulse._mem.update(at=0.0, data=None)
    monkeypatch.setattr(S, "_get", lambda *a, **k: (None, "HTTP 503"))
    out = pulse.find("")
    assert out["sources"]["hn_ask"]["state"] == "failed" and out["matches"] == []


GOOD = {"statement": "Freelancers lose hours chasing late invoices", "who": "solo freelancers", "workaround": "manual email reminders",
        "already_solved": "reminder tools exist but need setup", "who_is_missing": "freelancers who do not post online",
        "validation_plan": "ask 5 freelancers about the last late invoice", "kill_criteria": "most say they just ask once and get paid"}


def test_brief_flags_missing_fields_and_bad_labels():
    verify.remember("https://news.ycombinator.com/item?id=1", "Late payments", "I keep chasing invoices by hand and it wastes hours every week")
    bad = brief.check({"statement": "x", "evidence": [{"claim": "People chase invoices by hand", "url": "https://news.ycombinator.com/item?id=1", "label": "DOCUMENTED"}]})
    assert not bad["ok"]
    text = " ".join(bad["problems"])
    assert "missing: who" in text and "public post" in text


def test_brief_catches_invented_link_for_a_post_but_only_warns_for_official_page():
    ev = [{"claim": "Half of freelancers are paid late", "url": "https://reddit.com/r/x/comments/never-returned", "label": "HYPOTHESIS"},
          {"claim": "The regulator reports late payment rules", "url": "https://gov.example/report", "label": "DOCUMENTED"}]
    out = brief.check({**GOOD, "evidence": ev})
    assert not out["ok"] and any("never returned" in p for p in out["problems"])
    assert any("confirm it on the page yourself" in w for w in out["warnings"])


def test_brief_ok_when_complete_and_supported():
    verify.remember("https://news.ycombinator.com/item?id=1", "Late payments", "I keep chasing invoices by hand and it wastes hours every week")
    verify.remember("https://news.ycombinator.com/item?id=2", "Invoices", "I chase invoices by hand each week, wasting hours")
    ev = [{"claim": "People chase invoices by hand and waste hours", "url": "https://news.ycombinator.com/item?id=1", "label": "HYPOTHESIS"},
          {"claim": "People chase invoices by hand each week", "url": "https://news.ycombinator.com/item?id=2", "label": "HYPOTHESIS"}]
    out = brief.check({**GOOD, "evidence": ev})
    assert out["ok"], out
    assert any("no DOCUMENTED" in w for w in out["warnings"])
