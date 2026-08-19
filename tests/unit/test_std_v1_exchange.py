"""interop/std_v1/exchange.py tests: StdExchange's cross-thread mailbox.
Covers the None-keyed "accept on arrival" bucket for offers/audits
(spec Section 3/10) and, most importantly, the exact leftover-turn bug
`reset_turns()` exists to close -- a step-1 message from a previous
sub-game must never be mistaken for the new sub-game's own step-1 turn."""

import pytest

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.interop.std_v1.exchange import StdExchange


def test_wait_for_turn_returns_a_recorded_turn():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "move": "N"})
    assert exchange.wait_for_turn(1, timeout=0.2) == {"step": 1, "move": "N"}


def test_wait_for_turn_times_out_when_nothing_arrives():
    exchange = StdExchange(poll_interval=0.01)
    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_turn(1, timeout=0.05)


def test_reset_turns_prevents_a_leftover_message_from_the_previous_sub_game():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "sub_game": "old"})  # previous sub-game's own step 1
    exchange.reset_turns()
    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_turn(1, timeout=0.05)  # must not see the stale message


def test_offer_with_no_sub_game_number_is_accepted_for_any_wait():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"sub_game_number": None, "group_id": "peer"})
    assert exchange.wait_for_offer(3, timeout=0.2) == {"sub_game_number": None, "group_id": "peer"}


def test_offer_with_an_exact_sub_game_number_takes_priority_over_the_none_bucket():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_offer({"sub_game_number": None, "group_id": "generic"})
    exchange.record_offer({"sub_game_number": 2, "group_id": "specific"})
    assert exchange.wait_for_offer(2, timeout=0.2) == {"sub_game_number": 2, "group_id": "specific"}


def test_wait_for_consensus_reads_the_none_keyed_audit_bucket():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": None, "result_claim": "series_consensus"})
    assert exchange.wait_for_consensus(timeout=0.2) == {
        "sub_game_number": None,
        "result_claim": "series_consensus",
    }


def test_wait_for_consensus_skips_a_straggler_audit_missing_sub_game_number():
    # Real bug found live (yanell11 match): a final-sub-game audit
    # envelope that also omits sub_game_number lands in the same
    # None-keyed slot the real consensus envelope uses. The straggler
    # must not be mistaken for it -- this waits past it for the real one.
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": None, "result_claim": "capture", "records": []})

    import threading
    import time

    def _deliver_real_consensus_late():
        time.sleep(0.05)
        exchange.record_audit({"sub_game_number": None, "result_claim": "series_consensus", "consensus_sha": "a" * 64})

    threading.Thread(target=_deliver_real_consensus_late, daemon=True).start()

    result = exchange.wait_for_consensus(timeout=1.0)
    assert result["result_claim"] == "series_consensus"


def test_wait_for_consensus_times_out_if_only_a_straggler_ever_arrives():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": None, "result_claim": "survival", "records": []})

    import pytest

    from thief_peer.exceptions import DeadlineExceededError

    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_consensus(timeout=0.1)


def test_wait_for_audit_reads_the_none_keyed_bucket_when_no_records_to_check():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": None, "result_claim": "capture", "records": []})
    assert exchange.wait_for_audit(1, timeout=0.2)["result_claim"] == "capture"


def test_wait_for_audit_skips_a_same_slot_straggler_missing_sub_game_number():
    # Real bug found live (yanell11 match): their kit never populates the
    # audit envelope's own optional sub_game_number field at all, so every
    # one of their envelopes lands in the None-keyed slot. A stale one
    # from an earlier sub-game still sitting there when this side starts
    # waiting on the next one must not be mistaken for it -- confirmed
    # live: our sub-game-4 wait grabbed their sub-game-3 disclosure this
    # way. The records' own embedded sub_game_number (their convention:
    # inside payload) is what tells the two apart.
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({
        "sender": "police", "result_claim": "capture",
        "records": [{"payload": {"sub_game_number": 3, "step": 1, "type": "turn"}}],
    })

    import threading
    import time

    def _deliver_real_one_late():
        time.sleep(0.05)
        exchange.record_audit({
            "sender": "thief", "result_claim": "survival",
            "records": [{"payload": {"sub_game_number": 4, "step": 1, "type": "turn"}}],
        })

    threading.Thread(target=_deliver_real_one_late, daemon=True).start()

    result = exchange.wait_for_audit(4, timeout=1.0)
    assert result["sender"] == "thief"


def test_wait_for_audit_skips_a_straggler_via_our_own_top_level_record_convention():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({
        "sender": "thief", "result_claim": "capture",
        "records": [{"sub_game_number": 1, "payload": {"step": 1}}],
    })
    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_audit(2, timeout=0.05)


def test_wait_for_audit_prefers_the_exact_keyed_entry_over_the_none_bucket():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": None, "sender": "generic", "records": []})
    exchange.record_audit({"sub_game_number": 2, "sender": "specific", "records": []})
    assert exchange.wait_for_audit(2, timeout=0.2)["sender"] == "specific"


def test_wait_for_audit_times_out_if_only_a_straggler_ever_arrives():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({
        "sender": "police", "result_claim": "capture",
        "records": [{"payload": {"sub_game_number": 3, "step": 1}}],
    })
    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_audit(4, timeout=0.1)


def test_latest_control_returns_none_when_empty_then_the_most_recent_message():
    exchange = StdExchange(poll_interval=0.01)
    assert exchange.latest_control() is None
    exchange.record_control({"type": "pause"})
    exchange.record_control({"type": "resume"})
    assert exchange.latest_control() == {"type": "resume"}
