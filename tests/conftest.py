import pytest

from radar import ratelimit


@pytest.fixture(autouse=True)
def _no_shared_rate_limit(monkeypatch):
    """Tests use fake sources and make many calls. The limiter has its own tests, which switch it back on."""
    monkeypatch.setenv("RADAR_RATELIMIT", "0")
    for key in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "STACKEXCHANGE_KEY", "GITHUB_TOKEN", "OPENFDA_KEY"):
        monkeypatch.delenv(key, raising=False)  # provider budgets depend on keys; tests must not depend on the developer's shell
    ratelimit.limiter.reset()
    yield
    ratelimit.limiter.reset()
