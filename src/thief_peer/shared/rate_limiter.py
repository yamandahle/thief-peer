"""Rate-limiting primitives (PRD_7 §2.4, §3): the token-bucket + FIFO
queue + DOS detector chain feeding `shared/gatekeeper.py`'s single doorway.
All limits are constructor parameters -- never hardcoded module constants
(the standing "no magic values" rule).
"""

import time
from collections import deque
from typing import Any


class TokenBucket:
    """`tokens <- min(C, tokens + r*dt)`, refilled lazily at each call
    rather than via a background timer -- mathematically identical to
    continuous refill, deterministic to test (PRD_7 §4)."""

    def __init__(self, capacity: float, refill_rate: float):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = capacity
        self._last = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last = now


class RequestQueue:
    """Bounded FIFO -- overflow requests queue rather than silently drop
    (PRD_7 §2.4); depth is config-driven, never hardcoded."""

    def __init__(self, max_depth: int):
        self._max_depth = max_depth
        self._queue: deque[Any] = deque()

    def enqueue(self, item: Any) -> bool:
        if len(self._queue) >= self._max_depth:
            return False
        self._queue.append(item)
        return True

    def dequeue(self) -> Any:
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)


class DosDetector:
    """A circuit breaker, not a self-healing rate limit: tracks call
    frequency in a sliding window and hard-locks (stays locked) once an
    anomalous volume is seen -- protects the account *before* the service
    provider notices, not after (PRD_7 §2.4)."""

    def __init__(self, max_calls: int, window_seconds: float):
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._call_times: deque[float] = deque()
        self._locked = False

    def record_call(self) -> None:
        if self._locked:
            return
        now = time.monotonic()
        self._call_times.append(now)
        self._prune(now)
        if len(self._call_times) > self._max_calls:
            self._locked = True

    def _prune(self, now: float) -> None:
        while self._call_times and now - self._call_times[0] > self._window_seconds:
            self._call_times.popleft()

    @property
    def is_locked(self) -> bool:
        return self._locked
