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
