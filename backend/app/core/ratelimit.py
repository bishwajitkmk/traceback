"""In-process sliding-window rate limiter.

Sufficient for a single API process (the MVP deployment). With several
processes each enforces its own window, so the effective limit multiplies;
moving the counters to Redis is the planned follow-up (see ADR 0005).
"""

import math
import threading
import time
from collections import defaultdict, deque

from app.core.errors import RateLimited


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        """Record one request for `key`; raise RateLimited when over the limit."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, math.ceil(hits[0] + self.window - now))
                raise RateLimited(retry_after)
            hits.append(now)
            if len(self._hits) > 50_000:  # bound memory under key-spraying
                self._prune(now)

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Shared limiters. Limits are generous for real use and tight for abuse.
login_limiter = RateLimiter(limit=10, window_seconds=60)  # per IP + email
register_limiter = RateLimiter(limit=5, window_seconds=600)  # per IP
ingest_limiter = RateLimiter(limit=600, window_seconds=60)  # per project key
ci_limiter = RateLimiter(limit=120, window_seconds=60)  # per project key
waitlist_limiter = RateLimiter(limit=5, window_seconds=600)  # per IP

ALL_LIMITERS = [login_limiter, register_limiter, ingest_limiter, ci_limiter, waitlist_limiter]
