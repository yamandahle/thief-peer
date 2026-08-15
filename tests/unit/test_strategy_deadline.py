"""peer/strategy_deadline.py tests. Bounds the Strategy Module's own
move-computation time (book Appendix B: step_deadline_seconds) -- distinct
from the network-facing RoundExchange deadline."""

import time

import pytest

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.peer.strategy_deadline import run_with_deadline


def test_run_with_deadline_returns_the_result_when_it_finishes_in_time():
    result = run_with_deadline(lambda: "decision", timeout_sec=1.0)

    assert result == "decision"


def test_run_with_deadline_raises_deadline_exceeded_when_the_callable_hangs():
    def _hang():
        # Long enough to reliably exceed the 0.05s deadline below, short
        # enough that the orphaned daemon thread (never joined -- that's
        # the point) doesn't linger noisily into whatever test runs next.
        time.sleep(0.2)
        return "too late"

    with pytest.raises(DeadlineExceededError):
        run_with_deadline(_hang, timeout_sec=0.05)


def test_run_with_deadline_propagates_the_callables_own_exception():
    def _boom():
        raise ValueError("real bug in the strategy module")

    with pytest.raises(ValueError, match="real bug in the strategy module"):
        run_with_deadline(_boom, timeout_sec=1.0)
