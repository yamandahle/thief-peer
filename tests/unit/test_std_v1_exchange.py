"""interop/std_v1/exchange.py tests."""

import threading
import time

import pytest

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.interop.std_v1.exchange import StdExchange


def test_wait_for_turn_returns_a_recorded_message():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 3, "sender": "police"})
    assert exchange.wait_for_turn(3, timeout=1.0) == {"step": 3, "sender": "police"}


def test_wait_for_turn_times_out_when_never_recorded():
    exchange = StdExchange(poll_interval=0.01)
    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_turn(5, timeout=0.1)


def test_wait_for_turn_unblocks_once_another_thread_records_it():
    exchange = StdExchange(poll_interval=0.01)

    def _record_later():
        time.sleep(0.1)
        exchange.record_turn({"step": 7, "sender": "thief"})

    threading.Thread(target=_record_later, daemon=True).start()
    result = exchange.wait_for_turn(7, timeout=2.0)
    assert result["step"] == 7


def test_offer_matched_by_exact_sub_game_number():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"sub_game_number": 2, "group_id": "team-a"})
    assert exchange.wait_for_offer(2, timeout=1.0)["group_id"] == "team-a"


def test_offer_without_sub_game_number_is_accepted_on_arrival():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"group_id": "team-b"})  # no sub_game_number at all
    assert exchange.wait_for_offer(4, timeout=1.0)["group_id"] == "team-b"


def test_audit_envelope_matched_by_exact_sub_game_number():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": 1, "result_claim": "capture"})
    assert exchange.wait_for_audit(1, timeout=1.0)["result_claim"] == "capture"


def test_consensus_envelope_has_no_sub_game_number():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"result_claim": "series_consensus", "consensus_sha": "a" * 64})
    result = exchange.wait_for_consensus(timeout=1.0)
    assert result["result_claim"] == "series_consensus"


def test_latest_control_returns_none_when_nothing_recorded():
    exchange = StdExchange(poll_interval=0.01)
    assert exchange.latest_control() is None


def test_latest_control_returns_the_most_recent():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_control({"type": "a"})
    exchange.record_control({"type": "b"})
    assert exchange.latest_control() == {"type": "b"}


def test_reset_turns_clears_a_leftover_step_from_a_prior_sub_game():
    # Regression: found via a real two-repo match -- step numbers restart
    # at 1 every sub-game, so without reset_turns() a stale step-1 message
    # from sub-game 1 would be handed back instantly as sub-game 2's own.
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "sender": "police", "sub_game": "stale"})

    exchange.reset_turns()

    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_turn(1, timeout=0.1)


def test_reset_turns_does_not_touch_offers_or_audits():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"sub_game_number": 1, "group_id": "team-a"})
    exchange.record_audit({"sub_game_number": 1, "result_claim": "capture"})

    exchange.reset_turns()

    assert exchange.wait_for_offer(1, timeout=1.0)["group_id"] == "team-a"
    assert exchange.wait_for_audit(1, timeout=1.0)["result_claim"] == "capture"
