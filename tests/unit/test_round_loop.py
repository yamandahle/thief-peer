"""peer/round_loop.py tests. First direct unit tests of this shape (it was
previously only exercised via the full live-match integration test) --
added specifically to pin the docs/todoFIXMCP.md fix: send_commit/
send_reveal here were unguarded, unlike the cop_v1 round loop's identical
pair, so a transport failure mid-round propagated straight past the
book's own dedicated AWAITING_REVEAL -> TECHNICAL_LOSS edge to
PeerRuntime.run()'s outer catch-all instead."""

import pytest

from thief_peer.constants import Direction
from thief_peer.exceptions import DeadlineExceededError, TransportError
from thief_peer.peer.round_exchange import RoundExchange
from thief_peer.peer.round_loop import play_round
from thief_peer.peer.turn_fsm import TurnFsm
from thief_peer.strategy.brain_base import Decision


class _FakeState:
    position = (2, 2)
    step_count = 1


class _FakeTurnHandler:
    def __init__(self):
        self.state = _FakeState()

    def play_turn(self, opponent_scent_snapshot):
        return Decision(move_type=None, direction=Direction.N)


class _FakeTrashTalk:
    def generate_hint(self, step):
        return "cold"


class _FakeScent:
    def advance(self, cell):
        pass

    def snapshot(self):
        return {}


class _StubTransport:
    def __init__(self, fail_on=None):
        self.calls = []
        self._fail_on = fail_on

    def call(self, tool_name, payload):
        self.calls.append(tool_name)
        if tool_name == self._fail_on:
            raise TransportError(f"{tool_name} unreachable")
        return {"ok": True}


def test_play_round_declares_technical_loss_when_send_commit_fails():
    fsm = TurnFsm()

    record, next_scent, technical_loss, reason = play_round(
        1, _FakeTurnHandler(), fsm, _FakeScent(), _FakeTrashTalk(), RoundExchange(),
        _StubTransport(fail_on="commit_move"), "thief", 1.0, 1.0, {},
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    assert record["payload"]["move"] == "N"  # the sealed record still comes back
    assert reason is not None and "commit_move unreachable" in reason


def test_play_round_declares_technical_loss_when_send_reveal_fails():
    fsm = TurnFsm()

    record, next_scent, technical_loss, reason = play_round(
        1, _FakeTurnHandler(), fsm, _FakeScent(), _FakeTrashTalk(), RoundExchange(),
        _StubTransport(fail_on="reveal_move"), "thief", 1.0, 1.0, {},
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    assert reason is not None and "reveal_move unreachable" in reason


def test_play_round_declares_technical_loss_when_her_reveal_never_arrives():
    fsm = TurnFsm()

    record, next_scent, technical_loss, reason = play_round(
        1, _FakeTurnHandler(), fsm, _FakeScent(), _FakeTrashTalk(), RoundExchange(),
        _StubTransport(), "thief", 0.05, 1.0, {},
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    assert reason is not None and "reveal never arrived" in reason


def test_play_round_raises_deadline_exceeded_when_the_strategy_hangs():
    # Deliberately not caught inside play_round itself (no sealed record
    # exists yet) -- must propagate uncaught for PeerRuntime.run()'s outer
    # wrapper to handle, same contract as the cop_v1 round loop.
    import time

    class _HangingTurnHandler(_FakeTurnHandler):
        def play_turn(self, opponent_scent_snapshot):
            time.sleep(0.2)
            return super().play_turn(opponent_scent_snapshot)

    with pytest.raises(DeadlineExceededError):
        play_round(
            1, _HangingTurnHandler(), TurnFsm(), _FakeScent(), _FakeTrashTalk(),
            RoundExchange(), _StubTransport(), "thief", 1.0, 0.05, {},
        )
