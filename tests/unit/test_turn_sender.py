"""peer/turn_sender.py tests (PRD_8 §3). Builds the two book-literal
messages (commit hash only, then move+hint+scent with the nonce withheld)
and sends each through whatever transport exposes `.call(tool_name, payload)`
-- proven here against a spy, matching the `_StubPeerTransport` pattern
already used in test_handshake.py."""

from thief_peer.constants import Direction, MoveType
from thief_peer.peer.turn_sender import send_commit, send_reveal
from thief_peer.strategy.brain_base import Decision


class _SpyTransport:
    def __init__(self):
        self.calls = []
        self.retryable_flags = []

    def call(self, tool_name, payload, retryable=True):
        self.calls.append((tool_name, payload))
        self.retryable_flags.append(retryable)
        return {"ok": True}


def test_send_commit_sends_only_the_hash_via_commit_move():
    transport = _SpyTransport()
    sealed = {"nonce": "deadbeef-nonce", "commit": "deadbeef-hash"}

    result = send_commit(transport, step=3, sender="thief", sealed=sealed)

    assert result == {"ok": True}
    assert len(transport.calls) == 1
    tool_name, args = transport.calls[0]
    assert tool_name == "commit_move"
    assert args == {"payload": {"step": 3, "sender": "thief", "h_commit": "deadbeef-hash"}}
    assert "nonce" not in args["payload"]


def test_send_reveal_sends_move_hint_and_scent_via_reveal_move():
    transport = _SpyTransport()
    decision = Decision(
        move_type=MoveType.MOVE, direction=Direction.N, hint="heading up", verdict="truth"
    )

    result = send_reveal(
        transport, step=3, sender="thief", decision=decision, scent_snapshot={"1,1": 0.5}
    )

    assert result == {"ok": True}
    tool_name, args = transport.calls[0]
    assert tool_name == "reveal_move"
    assert args == {
        "payload": {
            "step": 3,
            "sender": "thief",
            "hint": "heading up",
            "scent_grid": {"1,1": 0.5},
            "move": "N",
            "intent": "truth",
        }
    }


def test_send_reveal_uses_stay_for_a_hold_decision():
    transport = _SpyTransport()
    decision = Decision(move_type=MoveType.HOLD, direction=None, hint="", verdict="truth")

    send_reveal(transport, step=1, sender="thief", decision=decision, scent_snapshot={})

    _, args = transport.calls[0]
    assert args["payload"]["move"] == "STAY"


def test_send_commit_and_send_reveal_are_never_retried():
    # infra/mcp_client.py's own docstring: a retried reveal could land on
    # the opponent's server twice and fold the same hint evidence into
    # their belief map twice -- both calls must opt out of retry.
    transport = _SpyTransport()
    sealed = {"nonce": "n", "commit": "c"}
    decision = Decision(move_type=MoveType.MOVE, direction=Direction.N, hint="h", verdict="truth")

    send_commit(transport, step=1, sender="thief", sealed=sealed)
    send_reveal(transport, step=1, sender="thief", decision=decision, scent_snapshot={})

    assert transport.retryable_flags == [False, False]
