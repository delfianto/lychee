"""A small thread-safe token-bucket rate limiter.

``acquire`` blocks the calling thread until the requested tokens are available;
``take`` is the lock-guarded core that returns the wait needed, so it's unit-
testable with a fake clock. Tokens may go transiently negative (borrowing), which
serialises concurrent callers behind the accumulated debt — good enough to keep
the MangaDex client under its ~5 req/s and 40/min limits.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._capacity = capacity if capacity is not None else rate
        self._tokens = self._capacity
        self._monotonic = monotonic
        self._updated = monotonic()
        self._lock = threading.Lock()

    def take(self, tokens: float = 1.0) -> float:
        """Consume ``tokens``; return seconds to wait before they're truly available (0 if now)."""
        with self._lock:
            now = self._monotonic()
            self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self._rate)
            self._updated = now
            self._tokens -= tokens
            return max(0.0, -self._tokens / self._rate)

    def acquire(self, tokens: float = 1.0) -> None:
        wait = self.take(tokens)
        if wait > 0:
            time.sleep(wait)
