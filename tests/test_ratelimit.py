import time

from radar import research
from radar.ratelimit import Limiter, _Bucket


def test_bucket_spends_then_refuses_then_refills():
    b = _Bucket(rate=50.0, capacity=2)
    assert b.take(1) and b.take(1)
    assert not b.take(1)
    time.sleep(0.05)
    assert b.take(1)


def test_bucket_can_wait_for_tokens():
    b = _Bucket(rate=100.0, capacity=1)
    assert b.take(1)
    assert b.take(1, wait=1.0)


def test_limiter_is_off_when_disabled(monkeypatch):
    monkeypatch.setenv("RADAR_RATELIMIT", "0")
    lim = Limiter()
    assert all(lim.take("arxiv") for _ in range(20))


def test_limiter_enforces_provider_burst(monkeypatch):
    monkeypatch.setenv("RADAR_RATELIMIT", "1")
    lim = Limiter()
    assert lim.take("arxiv")          # burst of one
    assert not lim.take("arxiv")      # next must wait ~3s
    assert lim.take("hn")             # other providers are independent


def test_keys_raise_the_budgets(monkeypatch):
    assert research.provider_budget("se") == 2 and research.provider_budget("github") == 1
    monkeypatch.setenv("STACKEXCHANGE_KEY", "k")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    assert research.provider_budget("se") == 4 and research.provider_budget("github") == 3


def test_exhausted_bucket_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("RADAR_RATELIMIT", "1")
    research.limiter.reset()
    monkeypatch.setattr(research.limiter, "take", lambda *a, **k: False)
    out = research.research("accounting invoices", force=True)
    assert any(c.get("rate_limited") for c in out["coverage"].values())
