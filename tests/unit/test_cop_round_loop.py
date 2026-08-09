"""interop/cop_round_loop.py tests. Fakes stand in for TurnHandler/
TrashTalk/ScentField/TurnFsm the same way `peer/round_loop.py` itself has
no direct unit test (only exercised via the full live-match integration
test) -- these are the first direct tests of this round shape."""

from thief_peer.constants import Direction
from thief_peer.interop.cop_round_loop import play_round_cop
from thief_peer.strategy.brain_base import Decision


class _FakeState:
    position = (2, 2)


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

    record, next_scent, technical_loss = play_round_cop(
        1, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(), transport, {}
    )

    assert technical_loss is False
    assert turn_handler.seen_scent == {"4,3": 0.62}
    assert next_scent == {"4,3": 0.62}
    tool_names = [name for name, _ in transport.calls]
    assert tool_names == ["share_scent_map", "receive_commit", "receive_reveal"]
    assert record["payload"]["move"] == "N"


def test_play_round_cop_falls_back_to_last_scent_when_pull_fails():
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport(fail_on="share_scent_map")

    record, next_scent, technical_loss = play_round_cop(
        1, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(), transport, {"1,1": 0.5}
    )

    assert technical_loss is False
    assert next_scent == {"1,1": 0.5}


def test_play_round_cop_declares_technical_loss_when_commit_fails():
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport(fail_on="receive_commit")
    fsm = _FakeTurnFsm()

    record, next_scent, technical_loss = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(), transport, {}
    )

    assert technical_loss is True
    assert "TECHNICAL_LOSS" in fsm.transitions


def test_play_round_cop_advances_this_sides_own_scent_field_at_its_own_position():
    turn_handler = _FakeTurnHandler()
    scent = _FakeScent()
    play_round_cop(1, turn_handler, _FakeTurnFsm(), scent, _FakeTrashTalk(), _StubTransport(), {})

    assert scent.advanced_at == (2, 2)
