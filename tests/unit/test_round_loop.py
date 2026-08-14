"""peer/round_loop.py tests. Fakes mirror test_cop_round_loop.py's style
for the sibling play_round_cop. First direct unit test of the hint carried
through their_reveal (book Ch.6.4, page 47) -- previously only exercised,
undetected, via the full live-match integration test."""

from thief_peer.constants import Direction
from thief_peer.exceptions import DeadlineExceededError
from thief_peer.peer.round_loop import play_round
from thief_peer.peer.turn_fsm import TurnFsm
from thief_peer.strategy.brain_base import Decision


class _FakeState:
    position = (2, 2)
    step_count = 1


class _FakeTurnHandler:
    def __init__(self):
        self.state = _FakeState()
        self.seen_scent = None
        self.seen_hint = None
        self.seen_own_scent = None

    def play_turn(self, opponent_scent_snapshot, opponent_hint_text="", own_scent_snapshot=None):
        self.seen_scent = opponent_scent_snapshot
        self.seen_hint = opponent_hint_text
        self.seen_own_scent = own_scent_snapshot
        return Decision(move_type=None, direction=Direction.N)


class _FakeTrashTalk:
    def generate_hint(self, step, verdict="truth"):
        return "cold"


class _FakeScent:
    def advance(self, cell):
        pass

    def snapshot(self):
        return {}


class _FakeTurnFsm:
    def __init__(self):
        self.transitions = []

    def transition(self, target):
        self.transitions.append(target)


class _FakeRoundExchange:
    def __init__(self, reveal=None, raises=None, commit_raises=None):
        self._reveal = reveal if reveal is not None else {}
        self._raises = raises
        self._commit_raises = commit_raises
        self.waited_on_commit_steps: list[int] = []

    def wait_for_commit(self, step, deadline):
        self.waited_on_commit_steps.append(step)
        if self._commit_raises:
            raise self._commit_raises
        return "fake-h-commit"

    def wait_for_reveal(self, step, deadline):
        if self._raises:
            raise self._raises
        return self._reveal


class _FakeTransport:
    def __init__(self):
        self.calls: list[str] = []

    def call(self, tool_name, payload, retryable=True):
        self.calls.append(tool_name)
        return {"acknowledged": True}


def test_play_round_passes_last_opponent_hint_into_turn_handler():
    turn_handler = _FakeTurnHandler()

    play_round(
        1,
        turn_handler,
        _FakeTurnFsm(),
        _FakeScent(),
        _FakeTrashTalk(),
        _FakeRoundExchange(),
        _FakeTransport(),
        "thief",
        5.0,
        {},
        last_opponent_hint="last seen west",
    )

    assert turn_handler.seen_hint == "last seen west"


def test_play_round_defaults_last_opponent_hint_to_empty_string():
    turn_handler = _FakeTurnHandler()

    play_round(
        1, turn_handler, _FakeTurnFsm(), _FakeScent(), _FakeTrashTalk(),
        _FakeRoundExchange(), _FakeTransport(), "thief", 5.0, {},
    )

    assert turn_handler.seen_hint == ""


def test_play_round_returns_the_opponents_new_hint_from_their_reveal():
    reveal = {"scent_grid": {"1,1": 0.5}, "hint": "near the north east corner"}

    record, next_scent, next_hint, technical_loss = play_round(
        1,
        _FakeTurnHandler(),
        _FakeTurnFsm(),
        _FakeScent(),
        _FakeTrashTalk(),
        _FakeRoundExchange(reveal=reveal),
        _FakeTransport(),
        "thief",
        5.0,
        {},
    )

    assert technical_loss is False
    assert next_scent == {"1,1": 0.5}
    assert next_hint == "near the north east corner"


def test_play_round_returns_empty_hint_when_reveal_omits_it():
    record, next_scent, next_hint, technical_loss = play_round(
        1,
        _FakeTurnHandler(),
        _FakeTurnFsm(),
        _FakeScent(),
        _FakeTrashTalk(),
        _FakeRoundExchange(reveal={"scent_grid": {}}),
        _FakeTransport(),
        "thief",
        5.0,
        {},
    )

    assert next_hint == ""


def test_play_round_carries_the_last_hint_forward_on_a_technical_loss():
    # Uses the REAL TurnFsm -- same reasoning as
    # test_cop_round_loop.py::test_play_round_cop_declares_technical_loss_when_commit_fails:
    # a fake FSM never enforces the book's legal-transition table.
    fsm = TurnFsm()

    record, next_scent, next_hint, technical_loss = play_round(
        1,
        _FakeTurnHandler(),
        fsm,
        _FakeScent(),
        _FakeTrashTalk(),
        _FakeRoundExchange(raises=DeadlineExceededError("no reveal")),
        _FakeTransport(),
        "thief",
        5.0,
        {"9,9": 0.1},
        last_opponent_hint="previous hint",
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    assert next_scent == {"9,9": 0.1}
    assert next_hint == "previous hint"


def test_play_round_waits_for_the_opponents_commit_before_revealing():
    # Book Fig. 6 (p.35-36): reveal must not happen until both sides are
    # locked in -- confirms the wait actually runs, keyed by this round's
    # step, and that the commit is sent before the reveal.
    round_exchange = _FakeRoundExchange()
    transport = _FakeTransport()

    play_round(
        4,
        _FakeTurnHandler(),
        _FakeTurnFsm(),
        _FakeScent(),
        _FakeTrashTalk(),
        round_exchange,
        transport,
        "thief",
        5.0,
        {},
    )

    assert round_exchange.waited_on_commit_steps == [4]
    assert transport.calls.index("commit_move") < transport.calls.index("reveal_move")


def test_play_round_declares_technical_loss_when_the_opponents_commit_never_arrives():
    # The actual bug this fix closes: revealing before confirming the
    # opponent locked in their own commit. Same legal-transition detour as
    # the reveal-timeout case above (COMMITTING has no direct edge to
    # TECHNICAL_LOSS in the book's own table, Ch.8 p.63).
    fsm = TurnFsm()
    transport = _FakeTransport()

    record, next_scent, next_hint, technical_loss = play_round(
        1,
        _FakeTurnHandler(),
        fsm,
        _FakeScent(),
        _FakeTrashTalk(),
        _FakeRoundExchange(commit_raises=DeadlineExceededError("no commit")),
        transport,
        "thief",
        5.0,
        {"5,5": 0.2},
        last_opponent_hint="earlier hint",
    )

    assert technical_loss is True
    assert fsm.state == "TECHNICAL_LOSS"
    assert next_scent == {"5,5": 0.2}
    assert next_hint == "earlier hint"
    assert "reveal_move" not in transport.calls  # never revealed without the opponent's commit
