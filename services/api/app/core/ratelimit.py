"""Per-tenant rate limiting for the expensive prospecting endpoints.

Website fetching, discovery and delivery all cost money or reach third parties,
so a single tenant must not be able to spend the whole budget in a loop. The
limiter is a fixed-window counter held in this process: it protects one worker
and is deliberately simple. A multi-worker deployment gets N times the limit,
which is documented rather than hidden — a shared limiter needs shared state
and that is a deployment decision, not a code default.
"""
from __future__ import annotations

import time
from threading import Lock


class RateLimitExceeded(Exception):
    def __init__(self, action: str, limit: int, retry_after_seconds: int):
        self.action = action
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit of {limit}/minute exceeded for {action}")


class FixedWindowRateLimiter:
    def __init__(self, window_seconds: int = 60, clock=time.monotonic):
        self._window = window_seconds
        self._clock = clock
        self._lock = Lock()
        self._hits: dict[tuple[str, str], tuple[float, int]] = {}

    def check(self, action: str, key: str, limit: int) -> None:
        """Count one use of ``action`` for ``key``; raise when over ``limit``."""
        if limit <= 0:  # 0 disables the limit for operators who front it elsewhere.
            return
        now = self._clock()
        with self._lock:
            window_start, count = self._hits.get((action, key), (now, 0))
            if now - window_start >= self._window:
                window_start, count = now, 0
            if count >= limit:
                retry_after = max(1, int(self._window - (now - window_start)))
                raise RateLimitExceeded(action, limit, retry_after)
            self._hits[(action, key)] = (window_start, count + 1)
            if len(self._hits) > 10_000:  # bound memory on a pathological key space
                self._evict_expired(now)

    def _evict_expired(self, now: float) -> None:
        for entry, (window_start, _) in list(self._hits.items()):
            if now - window_start >= self._window:
                del self._hits[entry]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = FixedWindowRateLimiter()
