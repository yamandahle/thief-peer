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

    def play_turn(self, opponent_scent_snapshot, opponent_hint_text=""):
        self.seen_scent = opponent_scent_snapshot
        self.seen_hint = opponent_hint_text
        return Decision(move_type=None, direction=Direction.N)


class _FakeTrashTalk:
    def generate_hint(self, step):
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
    def __init__(self, reveal=None, raises=None):
        self._reveal = reveal if reveal is not None else {}
        self._raises = raises

    def wait_for_reveal(self, step, deadline):
        if self._raises:
            raise self._raises
        return self._reveal


class _FakeTransport:
    def call(self, tool_name, payload):
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
