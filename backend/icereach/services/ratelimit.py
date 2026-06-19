"""In-memory fixed-window rate limiter (per-process).

Good enough for a single instance; a multi-instance deploy would back this with
Redis. `allow(key, limit)` returns (allowed, retry_after_seconds).
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, int], int] = {}

    def allow(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        if not limit:
            return True, 0
        now = now if now is not None else time.time()
        window = int(now // 60)
        bkey = (key, window)
        with self._lock:
            count = self._buckets.get(bkey, 0) + 1
            self._buckets[bkey] = count
            if len(self._buckets) > 50_000:  # opportunistic cleanup of old windows
                self._buckets = {k: v for k, v in self._buckets.items() if k[1] >= window}
        if count > limit:
            return False, 60 - int(now % 60)
        return True, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = RateLimiter()
