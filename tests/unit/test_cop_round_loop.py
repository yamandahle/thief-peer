"""interop/cop_round_loop.py tests. Fakes stand in for TurnHandler/
TrashTalk/ScentField/TurnFsm the same way `peer/round_loop.py` itself has
no direct unit test (only exercised via the full live-match integration
test) -- these are the first direct tests of this round shape."""

from thief_peer.constants import Direction
from thief_peer.exceptions import DeadlineExceededError
from thief_peer.interop.cop_round_loop import play_round_cop
from thief_peer.peer.turn_fsm import TurnFsm
from thief_peer.strategy.brain_base import Decision


class _FakeState:
    position = (2, 2)
    step_count = 1


class _FakeTurnHandler:
    def __init__(self):
        self.state = _FakeState()
        self.seen_scent = None
        self.seen_own_scent = None

    def play_turn(self, opponent_scent_snapshot, own_scent_snapshot=None):
        self.seen_scent = opponent_scent_snapshot
        self.seen_own_scent = own_scent_snapshot
        return Decision(move_type=None, direction=Direction.N)


class _FakeTrashTalk:
    def generate_hint(self, step, verdict="truth"):
        return "cold"


class _FakeScent:
    def __init__(self):
        self.advanced_at = None

    def advance(self, cell):
        self.advanced_at = cell

    def snapshot(self):
        return {}


class _FakeTurnFsm:
    def __init__(self):
        self.transitions = []

    def transition(self, target):
        self.transitions.append(target)


class _FakeRoundExchange:
    """Mirrors peer/round_exchange.py's real interface just enough for
    these tests -- commit_arrives=False simulates the opponent's commit
    never showing up within the deadline (real DeadlineExceededError)."""

    def __init__(self, commit_arrives: bool = True):
        self._commit_arrives = commit_arrives
        self.waited_on_steps: list[int] = []

    def wait_for_commit(self, step: int, timeout: float) -> str:
        self.waited_on_steps.append(step)
        if not self._commit_arrives:
            raise DeadlineExceededError(f"No commit received for step {step} within {timeout}s")
        return "fake-h-commit"


class _StubTransport:
    def __init__(self, scent_wire=None, fail_on=None):
        self.calls = []
        self._scent_wire = scent_wire if scent_wire is not None else {"cells": [[3, 4, 0.62]]}
        self._fail_on = fail_on

    def call(self, tool_name, payload, retryable=True):
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
        1, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(), transport, {},
        _FakeRoundExchange(), 5.0,
    )

    assert technical_loss is False
    assert turn_handler.seen_scent == {"4,3": 0.62}
    assert next_scent == {"4,3": 0.62}
    tool_names = [name for name, _ in transport.calls]
    assert tool_names == ["share_scent_map", "receive_commit", "receive_reveal"]
    assert record["payload"]["move"] == {"type": "move", "direction": "N"}
    assert record["payload"]["state"] == '{"barriers_placed":[],"own_pos":[2,2],"steps_taken":1}'
    assert record["payload"]["intent"] is True


def test_play_round_cop_waits_for_the_opponents_commit_before_revealing():
    # Book Fig. 6 (p.35-36): reveal must not happen until both sides are
    # locked in. Confirms the wait actually runs, keyed by this round's step.
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport()
    round_exchange = _FakeRoundExchange()

    play_round_cop(
        3, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(), transport, {},
        round_exchange, 5.0,
    )

    assert round_exchange.waited_on_steps == [3]
    tool_names = [name for name, _ in transport.calls]
    assert tool_names.index("receive_commit") < tool_names.index("receive_reveal")


def test_play_round_cop_falls_back_to_last_scent_when_pull_fails():
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport(fail_on="share_scent_map")

    record, next_scent, technical_loss = play_round_cop(
        1, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(), transport, {"1,1": 0.5},
        _FakeRoundExchange(), 5.0,
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

    record, next_scent, technical_loss = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(), transport, {},
        _FakeRoundExchange(), 5.0,
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"


def test_play_round_cop_declares_technical_loss_when_the_opponents_commit_never_arrives():
    # The actual bug this fix closes: revealing before confirming the
    # opponent locked in their own commit. Same legal-transition detour
    # as the send-failure case above (COMMITTING has no direct edge to
    # TECHNICAL_LOSS in the book's own table).
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport()
    fsm = TurnFsm()

    record, next_scent, technical_loss = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(), transport, {},
        _FakeRoundExchange(commit_arrives=False), 5.0,
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    tool_names = [name for name, _ in transport.calls]
    assert "receive_reveal" not in tool_names  # never revealed without the opponent's commit


def test_play_round_cop_declares_technical_loss_when_reveal_fails():
    turn_handler = _FakeTurnHandler()
    transport = _StubTransport(fail_on="receive_reveal")
    fsm = TurnFsm()

    record, next_scent, technical_loss = play_round_cop(
        1, turn_handler, fsm, _FakeScent(), _FakeTrashTalk(), transport, {},
        _FakeRoundExchange(), 5.0,
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"


def test_play_round_cop_advances_this_sides_own_scent_field_at_its_own_position():
    turn_handler = _FakeTurnHandler()
    scent = _FakeScent()
    play_round_cop(
        1, turn_handler, _FakeTurnFsm(), scent, _FakeTrashTalk(), _StubTransport(), {},
        _FakeRoundExchange(), 5.0,
    )

    assert scent.advanced_at == (2, 2)
