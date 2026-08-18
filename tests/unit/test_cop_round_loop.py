"""interop/cop_round_loop.py tests. Fakes stand in for TurnHandler/
TrashTalk/ScentField/TurnFsm the same way `peer/round_loop.py` itself has
no direct unit test (only exercised via the full live-match integration
test) -- these are the first direct tests of this round shape."""

import pytest

from thief_peer.constants import Direction
from thief_peer.interop.cop_round_loop import play_round_cop
from thief_peer.peer.round_exchange import RoundExchange
from thief_peer.peer.turn_fsm import TurnFsm
from thief_peer.strategy.brain_base import Decision


class _FakeState:
    position = (2, 2)
    step_count = 1


class _FakeTurnHandler:
    def __init__(self):
        self.state = _FakeState()
        self.seen_scent = None

    def play_turn(self, opponent_scent_snapshot):
        self.seen_scent = opponent_scent_snapshot
        return Decision(move_type=None, direction=Direction.N)


class _FakeTrashTalk:
    def generate_hint(self, step):
        return "cold"


class _FakeScent:
    def __init__(self):
        self.advanced_at = None

    def advance(self, cell):
        self.advanced_at = cell


class _FakeTurnFsm:
    def __init__(self):
        self.transitions = []

    def transition(self, target):
        self.transitions.append(target)


class _StubTransport:
    def __init__(self, scent_wire=None, fail_on=None):
        self.calls = []
        self._scent_wire = scent_wire if scent_wire is not None else {"cells": [[3, 4, 0.62]]}
        self._fail_on = fail_on

    def call(self, tool_name, payload):
        self.calls.append((tool_name, payload))
        if tool_name == self._fail_on:
            from thief_peer.exceptions import TransportError

            raise TransportError(f"{tool_name} unreachable")
        if tool_name == "share_scent_map":
            return self._scent_wire
        return {"acknowledged": True}


def test_play_round_cop_pulls_scent_before_deciding_then_commits_and_reveals():
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport()
    round_exchange = RoundExchange()
    round_exchange.record_reveal(1, {})  # her matching-round reveal already landed

    record, next_scent, technical_loss, reason = play_round_cop(
        1, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(),
        round_exchange, transport, 1.0, 1.0, {}
    )

    assert technical_loss is False
    assert turn_handler.seen_scent == {"4,3": 0.62}
    assert next_scent == {"4,3": 0.62}
    tool_names = [name for name, _ in transport.calls]
    assert tool_names == ["share_scent_map", "receive_commit", "receive_reveal"]
    assert record["payload"]["move"] == {"type": "move", "direction": "N"}
    assert record["payload"]["state"] == '{"barriers_placed":[],"own_pos":[2,2],"steps_taken":1}'
    assert record["payload"]["intent"] is True


def test_play_round_cop_falls_back_to_last_scent_when_pull_fails():
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport(fail_on="share_scent_map")
    round_exchange = RoundExchange()
    round_exchange.record_reveal(1, {})

    record, next_scent, technical_loss, reason = play_round_cop(
        1, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(),
        round_exchange, transport, 1.0, 1.0, {"1,1": 0.5}
    )

    assert technical_loss is False
    assert next_scent == {"1,1": 0.5}


def test_play_round_cop_declares_technical_loss_when_commit_fails():
    # Uses the REAL TurnFsm, not the fake -- the fake never enforced the
    # book's legal-transition table, which is exactly what let the original
    # bug (attempting COMMITTING -> TECHNICAL_LOSS directly, an illegal
    # edge -- only AWAITING_REVEAL -> TECHNICAL_LOSS exists) ship
    # undetected until an actual mid-match connection drop hit it live.
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport(fail_on="receive_commit")
    fsm = TurnFsm()

    record, next_scent, technical_loss, reason = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(),
        RoundExchange(), transport, 1.0, 1.0, {}
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    assert reason is not None and "receive_commit unreachable" in reason


def test_play_round_cop_declares_technical_loss_when_reveal_fails():
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport(fail_on="receive_reveal")
    fsm = TurnFsm()

    record, next_scent, technical_loss, reason = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(),
        RoundExchange(), transport, 1.0, 1.0, {}
    )

    assert technical_loss is True
    assert reason is not None and "receive_reveal unreachable" in reason
    assert fsm.state == "TECHNICAL_LOSS"


def test_play_round_cop_raises_deadline_exceeded_when_the_strategy_hangs():
    # Book Appendix B: step_deadline_seconds bounds our own local
    # decide()/hint-generation time, distinct from the network-facing
    # round_deadline_sec -- deliberately not caught inside play_round_cop
    # itself (no sealed record exists yet at this point), so this must
    # propagate uncaught for PeerRuntime.run()'s outer wrapper to handle.
    import time

    from thief_peer.exceptions import DeadlineExceededError

    class _HangingTurnHandler(_FakeTurnHandler):
        def play_turn(self, opponent_scent_snapshot):
            # Long enough to reliably exceed the 0.05s deadline below,
            # short enough that the orphaned daemon thread (never joined
            # -- that's the point) doesn't linger into whatever runs next.
            time.sleep(0.2)
            return super().play_turn(opponent_scent_snapshot)

    with pytest.raises(DeadlineExceededError):
        play_round_cop(
            1, _HangingTurnHandler(), _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(),
            RoundExchange(), _StubTransport(), 1.0, 0.05, {}
        )


def test_play_round_cop_declares_technical_loss_when_her_reveal_never_arrives():
    # The lockstep gate (book Ch.5.3.2/8.3): our own loop must not advance
    # past step N without proof she completed her own step N too -- a
    # real live match proved that missing wait let this side race ahead
    # to its own max_moves while she was still honestly mid-round.
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport()
    fsm = TurnFsm()

    record, next_scent, technical_loss, reason = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(),
        RoundExchange(), transport, 0.05, 1.0, {}
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    assert reason is not None and "reveal never arrived" in reason


def test_play_round_cop_does_not_declare_technical_loss_when_interrupted_by_a_confirmed_capture():
    # A confirmed capture (interop/cop_server_tools.py's
    # handle_receive_capture_claim) sets round_wakeup the instant it lands,
    # even mid-wait for a reveal that -- since she already ended her own
    # match on that same confirmation -- will never arrive. This must
    # return cleanly (not technical_loss), so the caller's own
    # _captured_by_landing check ends the match as "captured" instead of a
    # false timeout.
    import threading

    turn_handler = _FakeTurnHandler()
    transport = _StubTransport()
    fsm = TurnFsm()
    round_wakeup = threading.Event()
    round_wakeup.set()  # already confirmed by the time this round waits

    record, next_scent, technical_loss, reason = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(),
        RoundExchange(), transport, 5.0, 1.0, {}, round_wakeup,
    )

    assert technical_loss is False
    assert reason is None
    assert fsm.state == "WAITING_FOR_OPPONENT"


def test_play_round_cop_advances_this_sides_own_scent_field_at_its_own_position():
    turn_handler = _FakeTurnHandler()
    scent = _FakeScent()
    round_exchange = RoundExchange()
    round_exchange.record_reveal(1, {})
    play_round_cop(
        1, turn_handler, _FakeTurnFsm(), scent, _FakeTrashTalk(),
        round_exchange, _StubTransport(), 1.0, 1.0, {}
    )

    assert scent.advanced_at == (2, 2)
