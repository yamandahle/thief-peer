"""interop/std_v1/police_round_loop.py tests (std_v1's own alternated
Police role, spec Section 6). Unlike round_loop.py's Thief side, this
loop never touches TurnHandler at all -- movement comes straight from
police_brain.choose_police_move -- so no turn_handler fake is needed
here."""

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.police_round_loop import play_sub_game_as_police


class _FakeScent:
    def snapshot(self):
        return {}

    def advance(self, cell):
        pass


class _StubTransport:
    def __init__(self):
        self.sent = []

    def call(self, name, payload):
        self.sent.append((name, payload))
        return {"ok": True}


def test_play_sub_game_as_police_waits_for_the_thiefs_step_one_turn_first():
    state = OwnGameState(position=(0, 0))
    board = Board(size=7, barriers=set())
    exchange = StdExchange(poll_interval=0.01)
    # Never populated -- the loop must time out waiting for step 1, never
    # move first (spec Section 10: "the Thief sends the first turn").
    result, records, peer_commits, my_commits = play_sub_game_as_police(
        board, state, _FakeScent(), _StubTransport(), exchange,
        max_steps=35, turn_deadline_sec=0.05, thief_start=(3, 3),
    )
    assert result == "timeout"
    # records[0] is the sealed step-0 declaration (sealing.py::build_step0_record),
    # not a turn -- no police turn was ever sent before the timeout.
    assert len(records) == 1
    assert records[0]["payload"]["type"] == "system_spec"
    assert my_commits == {}


def test_play_sub_game_as_police_reports_capture_when_thief_confirms_caught():
    state = OwnGameState(position=(0, 0))
    board = Board(size=7, barriers=set())
    exchange = StdExchange(poll_interval=0.01)
    # Per-peer numbering: police's reply to thief step 1 is also step 1;
    # the thief's next message (its own step 2) carries the confirmation.
    exchange.record_turn({"step": 1, "commit": "c1", "smell_grid": {"0,1": 0.9}, "claim_response": None, "win_claim": None})
    exchange.record_turn({"step": 2, "commit": "c2", "smell_grid": {}, "claim_response": {"claim": [0, 1], "caught": True}, "win_claim": None})

    result, records, peer_commits, my_commits = play_sub_game_as_police(
        board, state, _FakeScent(), _StubTransport(), exchange,
        max_steps=35, turn_deadline_sec=0.2, thief_start=(3, 3),
    )

    assert result == "capture"
    assert peer_commits == {1: "c1", 2: "c2"}
    # records[0] is the sealed step-0 declaration; records[1] is the one
    # police turn sent (step 1) before the confirmation arrived.
    assert len(records) == 2
    assert records[0]["payload"]["type"] == "system_spec"
    assert records[1]["payload"]["step"] == 1
    assert set(my_commits) == {1}


def test_play_sub_game_as_police_reports_survival_when_the_thief_declares_it():
    state = OwnGameState(position=(0, 0))
    board = Board(size=7, barriers=set())
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "commit": "c1", "smell_grid": {}, "claim_response": None, "win_claim": None})
    exchange.record_turn({"step": 2, "commit": "c2", "smell_grid": {}, "claim_response": {"claim": [9, 9], "caught": False}, "win_claim": {"type": "survival"}})

    result, records, peer_commits, my_commits = play_sub_game_as_police(
        board, state, _FakeScent(), _StubTransport(), exchange,
        max_steps=35, turn_deadline_sec=0.2, thief_start=(3, 3),
    )

    assert result == "survival"


def test_play_sub_game_as_police_moves_toward_the_believed_thief_cell():
    state = OwnGameState(position=(0, 0))
    board = Board(size=7, barriers=set())
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn({"step": 1, "commit": "c1", "smell_grid": {"0,5": 0.9}, "claim_response": None, "win_claim": None})

    play_sub_game_as_police(
        board, state, _FakeScent(), _StubTransport(), exchange,
        max_steps=1, turn_deadline_sec=0.05, thief_start=(3, 3),
    )

    assert state.position == (0, 1)  # stepped east, toward the highest-scent cell (0,5)
