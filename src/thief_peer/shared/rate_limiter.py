"""Rate-limiting primitives (PRD_7 §2.4, §3): the Quota Manager + token-
bucket + FIFO queue + DOS detector chain feeding `shared/gatekeeper.py`'s
single doorway, in the book's own Figure 13 order (p.74, ch.9.3.1). All
limits are constructor parameters -- never hardcoded module constants
(the standing "no magic values" rule).
"""

import json
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
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


class QuotaManager:
    """Book's own Figure 13 (p.74, ch.9.3.1), first of the three gates: a
    counter of actions taken *today*, hard-blocking once the daily cap is
    reached -- "the last line of defense against account suspension: once
    the quota is exhausted, no further request goes out," even if the
    other two gates are somehow bypassed or misconfigured. Resets on a
    real UTC calendar-day boundary, not "N calls since this process
    started."

    Persists to disk (mirrors `report/report_writer.py::LeagueCounter`'s
    own read-check-save pattern, same default-path convention) rather
    than counting purely in memory -- a real Thief series spans 6 separate
    sub-game processes (PRD_10), each building its own fresh
    `ApiGatekeeper`; an in-memory-only counter would silently hand every
    sub-game its own full daily allowance instead of one shared across
    the whole day, which is the entire point of a *daily* cap.

    The book gives no concrete daily number anywhere in Appendix F /
    PARAMETERS.md's own parameter table -- only the architecture (this
    gate exists, first in the chain), never a value. `max_calls_per_day`
    is therefore a required, explicit constructor argument, never a
    baked-in default (I6/I9: never invent an ungrounded quantitative
    value) -- `shared/gatekeeper.py::ApiGatekeeper` itself leaves this
    gate optional (`quota_manager=None`, disabled) for exactly the same
    reason: wiring in an unrequested number would be inventing one."""

    def __init__(self, max_calls_per_day: int, path: str | Path = "results/quota_state.json"):
        self._max_calls_per_day = max_calls_per_day
        self._path = Path(path)

    def allow(self) -> bool:
        state = self._load()
        today = self._today()
        if state.get("day") != today:
            state = {"day": today, "count": 0}
        if state["count"] >= self._max_calls_per_day:
            return False
        state["count"] += 1
        self._save(state)
        return True

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state), encoding="utf-8")

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()
