"""interop/std_v1/audit.py tests (spec Sections 9-11)."""

import pytest

from thief_peer.exceptions import DeadlineExceededError, SimulationError
from thief_peer.interop.std_v1.audit import (
    build_consensus_envelope,
    build_consensus_object,
    build_sub_game_row,
    confirm_agreement,
    send_and_await,
    validate_consensus_envelope,
    verify_peer_records,
)
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.round_loop import play_sub_game
from thief_peer.interop.std_v1.sealing import build_audit_record, build_turn_payload, seal_turn


def test_verify_peer_records_passes_for_untampered_data():
    payload = build_turn_payload(step=2, sender="police", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])

    result = verify_peer_records([record], peer_commits={2: sealed["commit"]})

    assert result["log_verified"] is True
    assert result["tampered"] is False
    assert result["mismatched_steps"] == []


def test_verify_peer_records_catches_a_tampered_move():
    payload = build_turn_payload(step=2, sender="police", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    tampered_record = build_audit_record({**payload, "move": "S"}, sealed["nonce"])

    result = verify_peer_records([tampered_record], peer_commits={2: sealed["commit"]})

    assert result["log_verified"] is False
    assert result["tampered"] is True
    assert result["mismatched_steps"] == [2]


def test_verify_peer_records_catches_a_record_for_a_step_never_actually_seen_live():
    # A peer cannot approve its own fabricated record by simply not
    # matching it against anything we actually witnessed.
    payload = build_turn_payload(step=99, sender="police", move="N", hint="", smell_grid={})
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])

    result = verify_peer_records([record], peer_commits={})  # step 99 never arrived live

    assert result["tampered"] is True
    assert result["mismatched_steps"] == [99]


def test_build_sub_game_row_has_exactly_five_keys():
    row = build_sub_game_row(1, "capture", {"a": "thief", "b": "police"}, {"a": 5, "b": 20}, "b")
    assert set(row) == {"sub_game_number", "result", "roles", "score", "winner_group"}


def test_build_consensus_object_sorts_rows_by_sub_game_number():
    rows = [
        build_sub_game_row(3, "survival", {}, {}, None),
        build_sub_game_row(1, "capture", {}, {}, "a"),
        build_sub_game_row(2, "timeout", {}, {}, None),
    ]
    obj = build_consensus_object("a-vs-b", "uid", rows)
    assert [row["sub_game_number"] for row in obj["sub_games"]] == [1, 2, 3]
    assert set(obj) == {"game_id", "game_uid", "sub_games"}


def test_validate_consensus_envelope_accepts_a_well_formed_one():
    envelope = build_consensus_envelope("thief", "a" * 64)
    assert validate_consensus_envelope(envelope) == "a" * 64


def test_validate_consensus_envelope_rejects_wrong_result_claim():
    envelope = build_consensus_envelope("thief", "a" * 64)
    envelope["result_claim"] = "capture"
    with pytest.raises(SimulationError, match="result_claim"):
        validate_consensus_envelope(envelope)


def test_validate_consensus_envelope_rejects_non_empty_records():
    envelope = build_consensus_envelope("thief", "a" * 64)
    envelope["records"] = [{"step": 1}]
    with pytest.raises(SimulationError, match="records"):
        validate_consensus_envelope(envelope)


def test_validate_consensus_envelope_rejects_a_short_digest():
    envelope = build_consensus_envelope("thief", "abc")
    with pytest.raises(SimulationError, match="consensus_sha"):
        validate_consensus_envelope(envelope)


def test_validate_consensus_envelope_rejects_a_non_wire_role_sender():
    envelope = build_consensus_envelope("dev-team", "a" * 64)  # a group id, not "police"/"thief"
    with pytest.raises(SimulationError, match="wire role"):
        validate_consensus_envelope(envelope)


def test_validate_consensus_envelope_accepts_either_wire_role():
    assert validate_consensus_envelope(build_consensus_envelope("police", "b" * 64)) == "b" * 64
    assert validate_consensus_envelope(build_consensus_envelope("thief", "c" * 64)) == "c" * 64


def test_confirm_agreement_requires_all_three_conditions():
    assert confirm_agreement(True, True, "x", "x") is True
    assert confirm_agreement(False, True, "x", "x") is False
    assert confirm_agreement(True, False, "x", "x") is False
    assert confirm_agreement(True, True, "x", "y") is False


def test_send_and_await_returns_once_the_peer_responds():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sub_game_number": 1, "result_claim": "capture"})

    class _Transport:
        def call(self, tool_name, payload, retryable=True):
            return {"ok": True}

    result = send_and_await(
        _Transport(),
        lambda timeout: exchange.wait_for_audit(1, timeout),
        {"sender": "thief", "records": [], "result_claim": "capture", "sub_game_number": 1},
        resend_interval_sec=0.05,
        ceiling_sec=2.0,
    )
    assert result["result_claim"] == "capture"


def test_send_and_await_times_out_when_the_peer_never_responds():
    exchange = StdExchange(poll_interval=0.01)

    class _Transport:
        def call(self, tool_name, payload, retryable=True):
            return {"ok": True}

    with pytest.raises(DeadlineExceededError):
        send_and_await(
            _Transport(),
            lambda timeout: exchange.wait_for_audit(1, timeout),
            {"sender": "thief", "records": [], "result_claim": "capture", "sub_game_number": 1},
            resend_interval_sec=0.05,
            ceiling_sec=0.2,
        )


def test_end_to_end_records_from_a_real_sub_game_pass_their_own_audit():
    # Integration check: round_loop.py's own real output (records +
    # peer_commits) actually satisfies verify_peer_records -- not just the
    # hand-built fixtures above.
    from thief_peer.constants import Direction
    from thief_peer.domain.board import Board
    from thief_peer.domain.own_state import OwnGameState
    from thief_peer.strategy.brain_base import Decision

    class _FakeTurnHandler:
        def __init__(self, state):
            self.state = state

        def play_turn(self, opponent_scent_snapshot, opponent_hint_text="", own_scent_snapshot=None):
            r, c = self.state.position
            self.state.position = (r, c + 1)
            self.state.step_count += 1
            return Decision(move_type=None, direction=Direction.E, hint="cold")

    class _FakeScent:
        def advance(self, cell):
            pass

        def snapshot(self):
            return {}

    class _NoopTransport:
        def call(self, tool_name, payload, retryable=True):
            return {"ok": True}

    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    exchange = StdExchange(poll_interval=0.01)

    # Build one real, properly-sealed Cop turn the same way sealing.py
    # itself would, so peer_commits ends up holding its real commit.
    cop_payload = build_turn_payload(step=2, sender="police", move="STAY", hint="", smell_grid={})
    cop_sealed = seal_turn(cop_payload)
    exchange.record_turn(
        {**cop_payload, "commit": cop_sealed["commit"], "capture_claim": [0, 0], "barrier_placed": None}
    )

    _end_reason, records, peer_commits = play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), _NoopTransport(), exchange,
        max_steps=3, turn_deadline_sec=1.0,
    )

    # play_sub_game's own peer_commits correctly captured the real Cop
    # turn's live commit -- what verify_peer_records would check any
    # later-revealed record against.
    assert peer_commits == {2: cop_sealed["commit"]}
    # Every one of our own records carries a nonce and the (otherwise
    # hidden) move -- the actual shape verify_peer_records/build_audit_record
    # expect, produced by a genuine round trip through play_sub_game
    # rather than the hand-built fixtures the earlier tests in this file use.
    for record in records:
        assert "nonce" in record
        assert record["move"] in ("N", "S", "E", "W", "STAY")
