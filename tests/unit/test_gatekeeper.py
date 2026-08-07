"""shared/gatekeeper.py tests (PRD_7 §2.4, §3, §5). ApiGatekeeper is the
*sole* doorway `infra/email_sender.py` and `infra/llm_provider.py` are
allowed to be called through (PLAN.md ADR-4) -- every call attempt is
logged, gate or no gate."""

import pytest

from thief_peer.exceptions import ProviderError, RateLimitedError, TransportError
from thief_peer.shared.gatekeeper import ApiGatekeeper
from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket


def _gatekeeper(**overrides):
    defaults = {
        "token_bucket": TokenBucket(capacity=1, refill_rate=0.0),
        "dos_detector": DosDetector(max_calls=100, window_seconds=60),
        "queue": RequestQueue(max_depth=2),
        "max_retries": 3,
        "backoff_sec": 0.01,
        "poll_interval_sec": 0.01,
        "max_poll_attempts": 3,
    }
    defaults.update(overrides)
    return ApiGatekeeper(**defaults)


def test_execute_calls_the_api_when_a_token_is_available():
    gate = _gatekeeper()
    result = gate.execute(lambda x: x * 2, 21)
    assert result == 42


def test_execute_logs_a_successful_call():
    gate = _gatekeeper()
    gate.execute(lambda: "ok")
    assert gate.call_log[-1]["outcome"] == "success"
    assert "timestamp" in gate.call_log[-1]


def test_execute_raises_when_no_token_and_queue_is_immediately_full():
    bucket = TokenBucket(capacity=0, refill_rate=0.0)
    queue = RequestQueue(max_depth=0)
    gate = _gatekeeper(token_bucket=bucket, queue=queue)

    with pytest.raises(TransportError, match="queue"):
        gate.execute(lambda: "unreachable")


def test_execute_waits_for_a_refill_then_succeeds():
    bucket = TokenBucket(capacity=1, refill_rate=1000.0)  # refills almost instantly
    bucket.allow()  # drain it
    gate = _gatekeeper(token_bucket=bucket)

    result = gate.execute(lambda: "eventually")
    assert result == "eventually"


def test_execute_backs_off_and_retries_on_rate_limited_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RateLimitedError("429")
        return "ok"

    gate = _gatekeeper(max_retries=3)
    result = gate.execute(flaky)

    assert result == "ok"
    assert len(calls) == 3
    outcomes = [entry["outcome"] for entry in gate.call_log]
    assert outcomes.count("retry_rate_limited") == 2


def test_execute_gives_up_after_max_retries_on_persistent_rate_limiting():
    def always_429():
        raise RateLimitedError("429")

    gate = _gatekeeper(max_retries=2)
    with pytest.raises(ProviderError):
        gate.execute(always_429)


def test_execute_retries_once_on_a_generic_transient_failure_then_raises():
    calls = []

    def always_fails():
        calls.append(1)
        raise ConnectionError("boom")

    gate = _gatekeeper()
    with pytest.raises(ProviderError):
        gate.execute(always_fails)

    assert len(calls) == 2  # original + exactly one retry


def test_execute_succeeds_after_one_transient_failure():
    calls = []

    def fails_once():
        calls.append(1)
        if len(calls) < 2:
            raise ConnectionError("boom")
        return "recovered"

    gate = _gatekeeper()
    assert gate.execute(fails_once) == "recovered"


def test_execute_raises_immediately_when_dos_detector_is_already_locked():
    detector = DosDetector(max_calls=1, window_seconds=60)
    detector.record_call()
    detector.record_call()  # trips the lock
    assert detector.is_locked is True

    gate = _gatekeeper(dos_detector=detector)
    with pytest.raises(TransportError, match="locked"):
        gate.execute(lambda: "unreachable")


def test_every_call_attempt_is_logged_even_rejections():
    detector = DosDetector(max_calls=1, window_seconds=60)
    detector.record_call()
    detector.record_call()
    gate = _gatekeeper(dos_detector=detector)

    with pytest.raises(TransportError):
        gate.execute(lambda: "unreachable")

    assert len(gate.call_log) == 1
    assert gate.call_log[0]["outcome"] == "rejected_dos_lock"
