"""interop/std_v1/police_relay_loop.py tests -- std_v1's alternated Police
role sourced from a separate `yamanagh-cop` process's relay instead of
this repo's own built-in `police_brain.py` stand-in. Mirrors
`test_std_v1_police_round_loop.py`'s own fixtures/assertions; the only
real difference under test is that the move decision (and its seal) now
comes back from `relay_transport.call(...)` instead of being computed
locally."""

from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.police_relay_loop import play_sub_game_as_police


class _StubTransport:
    def __init__(self):
        self.sent = []

    def call(self, name, payload):
        self.sent.append((name, payload))
        return {"ok": True}


class _StubRelayTransport:
    """Stands in for `yamanagh-cop`'s relay -- records every call and
    returns a fresh, distinguishable decision each turn so tests can
    confirm the loop is really relaying (payload/nonce/commit sourced from
    here), not falling back to any local computation."""

    def __init__(self):
        self.calls = []
        self._step = 0

    def call(self, name, payload):
        self.calls.append((name, payload))
        if name == "start_police_subgame":
            return {"ok": True}
        self._step += 1
        return {
            "payload": {
                "step": payload["step"], "sender": "police", "move": "E", "hint": "",
                "smell_grid": {}, "barrier_placed": None, "capture_claim": [0, self._step],
                "claim_response": None, "win_claim": None,
            },
            "nonce": f"nonce-{self._step}",
            "commit": f"commit-{self._step}",
        }


def test_play_sub_game_as_police_waits_for_the_thiefs_step_one_turn_first():
    exchange = StdExchange(poll_interval=0.01)
    relay = _StubRelayTransport()
    result, records, peer_commits, my_commits = play_sub_game_as_police(
        _StubTransport(), exchange, max_steps=35, turn_deadline_sec=0.05,
        relay_transport=relay, sub_game_number=2,
    )
    assert result == "timeout"
    assert records == []
    assert my_commits == {}
    assert relay.calls[0][0] == "start_police_subgame"


def test_play_sub_game_as_police_reports_capture_when_thief_confirms_caught():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "commit": "c1", "smell_grid": {"0,1": 0.9}, "hint": "", "claim_response": None, "win_claim": None})
    exchange.record_turn({"step": 2, "commit": "c2", "smell_grid": {}, "hint": "", "claim_response": {"claim": [0, 1], "caught": True}, "win_claim": None})

    result, records, peer_commits, my_commits = play_sub_game_as_police(
        _StubTransport(), exchange, max_steps=35, turn_deadline_sec=0.2,
        relay_transport=_StubRelayTransport(), sub_game_number=2,
    )

    assert result == "capture"
    assert peer_commits == {1: "c1", 2: "c2"}
    assert len(records) == 1  # one relayed police turn (step 1) before the confirmation arrived
    assert my_commits == {1: "commit-1"}


def test_play_sub_game_as_police_reports_survival_when_the_thief_declares_it():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "commit": "c1", "smell_grid": {}, "hint": "", "claim_response": None, "win_claim": None})
    exchange.record_turn({"step": 2, "commit": "c2", "smell_grid": {}, "hint": "", "claim_response": {"claim": [9, 9], "caught": False}, "win_claim": {"type": "survival"}})

    result, *_ = play_sub_game_as_police(
        _StubTransport(), exchange, max_steps=35, turn_deadline_sec=0.2,
        relay_transport=_StubRelayTransport(), sub_game_number=2,
    )

    assert result == "survival"


def test_play_sub_game_as_police_sends_the_relayed_payload_over_the_wire():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "commit": "c1", "smell_grid": {}, "hint": "", "claim_response": None, "win_claim": None})
    transport = _StubTransport()
    relay = _StubRelayTransport()

    play_sub_game_as_police(
        transport, exchange, max_steps=1, turn_deadline_sec=0.05,
        relay_transport=relay, sub_game_number=3,
    )

    # start_police_subgame declares the right sub-game up front.
    assert relay.calls[0] == ("start_police_subgame", {"sub_game_number": 3})
    # The wire message sent out is built from the relay's own payload/commit.
    sent_name, sent_message = transport.sent[0]
    assert sent_name == "receive_turn"
    assert sent_message["message"]["commit"] == "commit-1"
    assert sent_message["message"]["capture_claim"] == [0, 1]
    assert "move" not in sent_message["message"]  # never sent live, spec Appendix D
