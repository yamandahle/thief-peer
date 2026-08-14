"""interop/cop_peer_audit.py — Ch.5.3.2 / rules 19/36 peer Hcommit audit."""

from thief_peer.domain.crypto import CommitReveal
from thief_peer.interop.cop_peer_audit import CopPeerTrace, audit_cop_peer_trace


def test_audit_passes_when_envelope_matches_replay():
    trace = CopPeerTrace()
    # Cop starts at [0,0], moves East → [1,0] at step 1
    state = '{"barriers_placed":[],"own_pos":[1,0],"steps_taken":1}'
    move = {"type": "move", "direction": "E"}
    payload = {
        "state": state,
        "move": move,
        "intent": True,
        "hint_text": "hi",
        "step": 1,
        "role": "cop",
    }
    sealed = CommitReveal.seal(payload)
    trace.record_commit(sealed["commit"])
    trace.record_reveal(move, "hi")
    trace.record_final_reveal({"1": sealed["nonce"]}, {"1": True})

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7, max_barriers=14)

    assert result["passed"] is True
    assert result["verified_steps"] == 1
    assert result["failed_steps"] == []


def test_audit_fails_on_hcommit_mismatch():
    trace = CopPeerTrace()
    trace.record_commit("0" * 64)
    trace.record_reveal({"type": "move", "direction": "E"}, "hi")
    trace.record_final_reveal({"1": "n" * 32}, {"1": True})

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7, max_barriers=14)

    assert result["passed"] is False
    assert 1 in result["failed_steps"]


def _sealed_step(step: int, state: str, move: dict, intent: bool = True, hint_text: str = "hi"):
    payload = {"state": state, "move": move, "intent": intent, "hint_text": hint_text, "step": step, "role": "cop"}
    return payload, CommitReveal.seal(payload)


def test_audit_fails_when_the_claimed_move_is_off_board_even_if_the_hash_is_honest():
    # Book ch.3's own Implementation Tip: an illegal claimed move must be
    # detected, not silently clamped to "stayed still" and waved through
    # just because the hash honestly matches what was actually claimed.
    trace = CopPeerTrace()
    # Cop starts at [0,0]; claims "West" -- off the board in that direction.
    # _apply leaves position unchanged on an illegal move, matching the
    # state string below exactly (this is about legality, not the hash).
    state = '{"barriers_placed":[],"own_pos":[0,0],"steps_taken":1}'
    move = {"type": "move", "direction": "W"}
    _payload, sealed = _sealed_step(1, state, move)
    trace.record_commit(sealed["commit"])
    trace.record_reveal(move, "hi")
    trace.record_final_reveal({"1": sealed["nonce"]}, {"1": True})

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7, max_barriers=14)

    assert result["passed"] is False
    assert 1 in result["failed_steps"]


def test_audit_fails_when_a_barrier_is_placed_off_board():
    trace = CopPeerTrace()
    state = '{"barriers_placed":[],"own_pos":[0,0],"steps_taken":1}'
    move = {"type": "place_barrier", "col": 99, "row": 99}
    _payload, sealed = _sealed_step(1, state, move)
    trace.record_commit(sealed["commit"])
    trace.record_reveal(move, "hi")
    trace.record_final_reveal({"1": sealed["nonce"]}, {"1": True})

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7, max_barriers=14)

    assert result["passed"] is False
    assert 1 in result["failed_steps"]


def test_audit_fails_when_a_barrier_exceeds_the_agreed_cap():
    # max_barriers=1: the second legal, on-board barrier still exceeds the
    # cap and must fail the audit (rule 12 [FATAL]).
    trace = CopPeerTrace()
    state1 = '{"barriers_placed":[[1,1]],"own_pos":[0,0],"steps_taken":1}'
    move1 = {"type": "place_barrier", "col": 1, "row": 1}
    _payload1, sealed1 = _sealed_step(1, state1, move1)
    state2 = '{"barriers_placed":[[1,1]],"own_pos":[0,0],"steps_taken":2}'
    move2 = {"type": "place_barrier", "col": 2, "row": 2}
    _payload2, sealed2 = _sealed_step(2, state2, move2)

    trace.record_commit(sealed1["commit"])
    trace.record_commit(sealed2["commit"])
    trace.record_reveal(move1, "hi")
    trace.record_reveal(move2, "hi")
    trace.record_final_reveal(
        {"1": sealed1["nonce"], "2": sealed2["nonce"]}, {"1": True, "2": True}
    )

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7, max_barriers=1)

    assert result["passed"] is False
    assert result["failed_steps"] == [2]  # the first barrier was legal; only the second exceeds the cap
