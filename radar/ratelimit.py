"""Shared, per-provider rate limiting for a public server.

All users of a hosted server share one IP and one set of API keys, so the real protection has to be a *shared*
limiter, not a small flat cap on every call. Each provider gets a token bucket sized to its documented allowance
(see PROVIDER_LIMITS). A search takes tokens before it calls out; when a bucket is empty the job is skipped and the
result says so, so heavy traffic degrades to cached answers instead of making every search thin.

Set RADAR_RATELIMIT=0 to disable (tests, local single-user use). Set RADAR_RATE_WAIT=<seconds> to wait for tokens
instead of skipping, which is what the scheduled refresh job does.
"""
from __future__ import annotations

import os
import threading
import time


def _has(*names: str) -> bool:
    return all(os.environ.get(n) for n in names)


def provider_limits() -> dict[str, tuple[float, float]]:
    """provider -> (tokens per second, burst capacity). Read at first use, so env keys decide the allowance.

    The numbers come from each provider's published limits, kept below them on purpose because every user of a
    public server shares them:
      Hacker News (Algolia)  10,000 requests/hour per IP
      Reddit OAuth           60 requests/minute per client (Reddit's published limit)
      Stack Exchange         300/day per IP without a key, 10,000/day with one
      GitHub                 60/hour without a token, search 30/minute with one
      openFDA                1,000/day per IP without a key, far more with one
      arXiv                  one request every 3 seconds
    """
    return {
        "hn": (2.0, 30),
        "reddit": (1.0, 20) if _has("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET") else (0.1, 4),
        "se": (0.09, 30) if _has("STACKEXCHANGE_KEY") else (0.0033, 8),
        "github": (0.3, 10) if _has("GITHUB_TOKEN") else (0.0166, 3),
        "gitlab": (0.5, 5),
        "europepmc": (2.0, 20),
        "scholar": (3.0, 20),
        "arxiv": (0.33, 1),
        "fda_devices": (0.9, 30) if _has("OPENFDA_KEY") else (0.0115, 30),
        "petitions": (1.0, 5),
        "nyc311": (1.0, 5),
        "bluesky": (0.5, 3),
        "gdelt": (0.2, 2),  # GDELT asks for about one request every five seconds
        "ckan": (1.0, 6),
    }


DEFAULT_LIMIT = (1.0, 5)


class _Bucket:
    def __init__(self, rate: float, capacity: float):
        self.rate, self.capacity = rate, capacity
        self.tokens, self.stamp = float(capacity), time.monotonic()
        self.lock = threading.Lock()

    def take(self, n: float, wait: float = 0.0) -> bool:
        deadline = time.monotonic() + max(0.0, wait)
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.rate)
                self.stamp = now
                if self.tokens >= n:
                    self.tokens -= n
                    return True
                need = (n - self.tokens) / self.rate if self.rate > 0 else float("inf")
            if now + need > deadline:
                return False
            time.sleep(min(need, 1.0))

    def level(self) -> float:
        with self.lock:
            now = time.monotonic()
            return min(self.capacity, self.tokens + (now - self.stamp) * self.rate)


class Limiter:
    def __init__(self):
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def enabled(self) -> bool:
        return os.environ.get("RADAR_RATELIMIT", "1") != "0"

    def take(self, provider: str, cost: float = 1.0, wait: float | None = None) -> bool:
        if not self.enabled():
            return True
        if wait is None:
            try:
                wait = float(os.environ.get("RADAR_RATE_WAIT", "0"))
            except ValueError:
                wait = 0.0
        with self._lock:
            bucket = self._buckets.get(provider)
            if bucket is None:
                rate, cap = provider_limits().get(provider, DEFAULT_LIMIT)
                bucket = self._buckets[provider] = _Bucket(rate, cap)
        # a request costing more than the whole bucket can never succeed; cap it so it can at least run when full
        return bucket.take(min(cost, bucket.capacity), wait)

    def snapshot(self) -> dict:
        return {p: round(b.level(), 2) for p, b in self._buckets.items()}

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = Limiter()
