"""shared/rate_limiter.py tests (PRD_7 §2.4, §3). The token bucket refills
lazily on each call (elapsed-time top-up), not via a background timer --
mathematically identical to continuous refill, deterministic to test with
no sleeping (PRD_7 §4)."""

import time
from datetime import UTC, datetime

from thief_peer.shared.rate_limiter import DosDetector, QuotaManager, RequestQueue, TokenBucket


def test_token_bucket_starts_full_and_allows_up_to_capacity():
    bucket = TokenBucket(capacity=3, refill_rate=0.0)
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is False


def test_token_bucket_refills_lazily_based_on_elapsed_time(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("thief_peer.shared.rate_limiter.time.monotonic", lambda: clock[0])

    bucket = TokenBucket(capacity=5, refill_rate=2.0)  # 2 tokens/sec
    for _ in range(5):
        bucket.allow()
    assert bucket.allow() is False  # empty

    clock[0] += 1.0  # 1 second passes -> +2 tokens
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is False


def test_token_bucket_never_exceeds_capacity_even_after_a_long_idle_period(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("thief_peer.shared.rate_limiter.time.monotonic", lambda: clock[0])

    bucket = TokenBucket(capacity=3, refill_rate=10.0)
    clock[0] += 1000.0  # would refill far past capacity without clamping

    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is False


def test_token_bucket_respects_a_custom_cost_per_call():
    bucket = TokenBucket(capacity=5, refill_rate=0.0)
    assert bucket.allow(cost=2.0) is True
    assert bucket.allow(cost=2.0) is True
    assert bucket.allow(cost=2.0) is False  # only 1 left


def test_request_queue_enqueues_up_to_max_depth_then_rejects():
    queue = RequestQueue(max_depth=2)
    assert queue.enqueue("a") is True
    assert queue.enqueue("b") is True
    assert queue.enqueue("c") is False
    assert len(queue) == 2


def test_request_queue_is_first_in_first_out():
    queue = RequestQueue(max_depth=3)
    queue.enqueue("a")
    queue.enqueue("b")
    assert queue.dequeue() == "a"
    assert queue.dequeue() == "b"
    assert queue.dequeue() is None


def test_dos_detector_stays_unlocked_under_the_threshold():
    detector = DosDetector(max_calls=5, window_seconds=60)
    for _ in range(5):
        detector.record_call()
    assert detector.is_locked is False


def test_dos_detector_locks_when_call_volume_spikes_past_the_threshold():
    detector = DosDetector(max_calls=5, window_seconds=60)
    for _ in range(6):
        detector.record_call()
    assert detector.is_locked is True


def test_dos_detector_stays_locked_once_tripped_even_if_calls_stop():
    # A circuit breaker, not a self-healing rate limit -- once it trips,
    # it stays tripped (an operator must notice and restart), matching the
    # book's "hard-lock" framing (PRD_7 §2.4).
    detector = DosDetector(max_calls=2, window_seconds=60)
    for _ in range(3):
        detector.record_call()
    assert detector.is_locked is True
    detector.record_call()
    assert detector.is_locked is True


def test_dos_detector_only_counts_calls_within_the_sliding_window(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("thief_peer.shared.rate_limiter.time.monotonic", lambda: clock[0])

    detector = DosDetector(max_calls=3, window_seconds=10)
    detector.record_call()
    detector.record_call()
    clock[0] += 20.0  # old calls age out of the window
    detector.record_call()
    detector.record_call()

    assert detector.is_locked is False


def test_dos_detector_uses_real_time_by_default():
    # Sanity check against the real clock, not just the monkeypatched one.
    detector = DosDetector(max_calls=100, window_seconds=1)
    detector.record_call()
    assert detector.is_locked is False
    time.sleep(0)  # no-op, just confirms real time.monotonic() doesn't error


def test_quota_manager_allows_up_to_the_daily_cap_then_blocks(tmp_path):
    quota = QuotaManager(max_calls_per_day=3, path=tmp_path / "quota.json")
    assert quota.allow() is True
    assert quota.allow() is True
    assert quota.allow() is True
    assert quota.allow() is False


def test_quota_manager_stays_blocked_for_the_rest_of_the_day(tmp_path):
    quota = QuotaManager(max_calls_per_day=1, path=tmp_path / "quota.json")
    assert quota.allow() is True
    assert quota.allow() is False
    assert quota.allow() is False  # doesn't self-heal within the same day


class _FakeDatetimeAt:
    """Stands in for the module's `datetime` name so QuotaManager's real
    UTC-calendar-day logic can be tested without waiting for a real
    midnight -- `_current` is swapped mid-test to simulate a day boundary."""

    def __init__(self, current: datetime):
        self._current = current

    def now(self, tz=None):
        return self._current


def test_quota_manager_resets_on_a_real_utc_calendar_day_boundary(monkeypatch, tmp_path):
    import thief_peer.shared.rate_limiter as rate_limiter_module

    fake = _FakeDatetimeAt(datetime(2026, 8, 14, 23, 59, tzinfo=UTC))
    monkeypatch.setattr(rate_limiter_module, "datetime", fake)

    quota = QuotaManager(max_calls_per_day=1, path=tmp_path / "quota.json")
    assert quota.allow() is True
    assert quota.allow() is False  # exhausted for 2026-08-14

    fake._current = datetime(2026, 8, 15, 0, 1, tzinfo=UTC)  # crossed midnight UTC
    assert quota.allow() is True  # fresh quota for the new calendar day


def test_quota_manager_persists_the_days_count_across_a_process_restart(tmp_path):
    # A real Thief series spans 6 separate sub-game processes (PRD_10),
    # each building its own fresh ApiGatekeeper/QuotaManager -- the whole
    # point of a *daily* cap is that a process restart mid-day must not
    # silently hand back a fresh allowance. Two instances sharing the same
    # path simulate that: the second must see the first's usage.
    path = tmp_path / "quota.json"
    quota_process_1 = QuotaManager(max_calls_per_day=2, path=path)
    assert quota_process_1.allow() is True

    quota_process_2 = QuotaManager(max_calls_per_day=2, path=path)  # "process restart"
    assert quota_process_2.allow() is True  # the shared day's 2nd (and last) call
    assert quota_process_2.allow() is False  # cap already spent by process 1 + this one
