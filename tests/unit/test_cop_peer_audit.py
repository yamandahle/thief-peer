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

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7)

    assert result["passed"] is True
    assert result["verified_steps"] == 1
    assert result["failed_steps"] == []


def test_audit_fails_on_hcommit_mismatch():
    trace = CopPeerTrace()
    trace.record_commit("0" * 64)
    trace.record_reveal({"type": "move", "direction": "E"}, "hi")
    trace.record_final_reveal({"1": "n" * 32}, {"1": True})

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7)

    assert result["passed"] is False
    assert 1 in result["failed_steps"]


def _seal_and_record_step1(trace: CopPeerTrace) -> None:
    # Cop starts at [0,0], moves East -> [1,0] at step 1 (same replay as
    # test_audit_passes_when_envelope_matches_replay).
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


def test_audit_passes_when_capture_claim_matches_replayed_position():
    trace = CopPeerTrace()
    _seal_and_record_step1(trace)
    # Her audited position after step 1 is (col=1, row=0) -- claiming a
    # capture from exactly that cell is truthful.
    trace.record_capture_claim(
        claimed_at_step=1, thief_row=9, thief_col=9, cop_row=0, cop_col=1, confirmed=True
    )

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7)

    assert result["passed"] is True
    assert result["failed_capture_claims"] == []


def test_audit_fails_when_capture_claim_lies_about_position():
    trace = CopPeerTrace()
    _seal_and_record_step1(trace)
    # She actually is at (col=1, row=0) per her own committed/revealed
    # trajectory, but claims a capture from clear across the board.
    trace.record_capture_claim(
        claimed_at_step=1, thief_row=9, thief_col=9, cop_row=5, cop_col=5, confirmed=True
    )

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7)

    assert result["passed"] is False
    assert result["failed_capture_claims"] == [1]


def test_audit_fails_on_capture_claim_for_an_unaudited_step():
    trace = CopPeerTrace()
    _seal_and_record_step1(trace)
    # Claims a capture at a step no commit/reveal was ever recorded for --
    # unverifiable, so it can't be trusted either.
    trace.record_capture_claim(
        claimed_at_step=2, thief_row=9, thief_col=9, cop_row=1, cop_col=1, confirmed=True
    )

    result = audit_cop_peer_trace(trace, cop_start=[0, 0], grid_size=7)

    assert result["passed"] is False
    assert result["failed_capture_claims"] == [2]
