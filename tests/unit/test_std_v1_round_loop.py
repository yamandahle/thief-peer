"""interop/std_v1/round_loop.py tests (Thief role, spec Sections 5/9/10).
Fakes stand in for TurnHandler/TrashTalk/ScentField the same way
test_cop_round_loop.py already does for the cop_v1 protocol's identical
situation -- these are the first direct tests of this round shape."""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.round_loop import play_sub_game
from thief_peer.strategy.brain_base import Decision


class _FakeTurnHandler:
    def __init__(self, state, directions):
        self.state = state
        self._directions = iter(directions)
        self.seen_scents = []

    def play_turn(self, opponent_scent_snapshot):
        self.seen_scents.append(opponent_scent_snapshot)
        direction = next(self._directions, None)
        return Decision(move_type=None, direction=direction)


class _FakeTrashTalk:
    def generate_hint(self, step):
        return f"hint-{step}"


class _FakeScent:
    def __init__(self):
        self.advanced_at = []

    def advance(self, cell):
        self.advanced_at.append(cell)

    def snapshot(self):
        return {}


class _StubTransport:
    def __init__(self):
        self.sent = []

    def call(self, name, payload):
        self.sent.append((name, payload))
        return {"ok": True}


def test_play_sub_game_survives_when_it_reaches_max_steps_uncaught():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    turn_handler = _FakeTurnHandler(state, [Direction.N, Direction.N])
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 2, "commit": "c2", "capture_claim": [0, 0], "barrier_placed": None, "smell_grid": {}})

    result, records, peer_commits = play_sub_game(
        turn_handler, board, state, _FakeScent(), _FakeTrashTalk(),
        _StubTransport(), exchange, max_steps=1, turn_deadline_sec=0.2,
    )

    assert result == "survival"
    assert len(records) == 1
    assert records[0]["step"] == 1


def test_play_sub_game_reports_capture_when_the_cops_claim_lands():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    turn_handler = _FakeTurnHandler(state, [Direction.N])
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({
        "step": 2, "commit": "c2", "capture_claim": [3, 3], "barrier_placed": None, "smell_grid": {},
    })

    result, records, peer_commits = play_sub_game(
        turn_handler, board, state, _FakeScent(), _FakeTrashTalk(),
        _StubTransport(), exchange, max_steps=35, turn_deadline_sec=0.2,
    )

    assert result == "capture"
    assert peer_commits == {2: "c2"}
    # A final STAY turn is sent carrying the truthful claim_response.
    assert records[-1]["claim_response"] == {"claim": [3, 3], "caught": True}
    assert records[-1]["move"] == "STAY"


def test_play_sub_game_times_out_when_the_cop_never_answers():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    turn_handler = _FakeTurnHandler(state, [Direction.N])
    exchange = StdExchange(poll_interval=0.01)

    result, records, peer_commits = play_sub_game(
        turn_handler, board, state, _FakeScent(), _FakeTrashTalk(),
        _StubTransport(), exchange, max_steps=35, turn_deadline_sec=0.05,
    )

    assert result == "timeout"
    assert peer_commits == {}


def test_play_sub_game_records_a_barrier_into_state_before_evaluating_capture():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    turn_handler = _FakeTurnHandler(state, [Direction.N])
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({
        "step": 2, "commit": "c2", "capture_claim": [0, 0], "barrier_placed": [3, 3], "smell_grid": {},
    })

    result, records, peer_commits = play_sub_game(
        turn_handler, board, state, _FakeScent(), _FakeTrashTalk(),
        _StubTransport(), exchange, max_steps=35, turn_deadline_sec=0.2,
    )

    assert result == "capture"  # barrier landed on the thief's own cell
    assert (3, 3) in state.known_barriers
