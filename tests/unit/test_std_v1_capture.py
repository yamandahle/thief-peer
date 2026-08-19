"""interop/std_v1/capture.py tests: the three terminal capture conditions
(spec Section 5 A/B/C) reuse this repo's own already-tested domain/rules.py
predicates directly."""

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.interop.std_v1.capture import build_claim_response, evaluate_capture


def test_evaluate_capture_true_on_direct_claim_co_location():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    assert evaluate_capture(state, board, [3, 3], barrier_placed=None) is True


def test_evaluate_capture_false_when_claim_misses_and_no_barrier():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    assert evaluate_capture(state, board, [1, 1], barrier_placed=None) is False


def test_evaluate_capture_true_when_barrier_lands_on_thief_cell():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    assert evaluate_capture(state, board, [1, 1], barrier_placed=[3, 3]) is True


def test_evaluate_capture_true_when_barrier_placement_leaves_thief_stuck():
    barriers = {(2, 3), (4, 3), (3, 4)}
    state = OwnGameState(position=(3, 3))
    for cell in barriers:
        state.record_barrier(cell)
    board = Board(size=7, barriers=barriers | {(3, 2)})
    # Caller contract: barrier_placed's cell must already be recorded into
    # known_barriers before evaluate_capture runs (condition C is defined
    # as "after the declared barrier is applied").
    state.record_barrier((3, 2))
    assert evaluate_capture(state, board, [1, 1], barrier_placed=[3, 2]) is True


def test_evaluate_capture_false_when_barrier_placed_elsewhere_and_thief_not_stuck():
    state = OwnGameState(position=(3, 3))
    board = Board(size=7, barriers=set())
    assert evaluate_capture(state, board, [1, 1], barrier_placed=[0, 0]) is False


def test_evaluate_capture_true_when_stuck_by_an_older_barrier_and_no_new_one_this_turn():
    # Real gap found via moamteam's own interop brief (their D6): a barrier
    # placed on an EARLIER turn can box this side in on a LATER turn where
    # the Cop doesn't declare a new barrier at all -- condition C must be
    # checked every turn regardless of `barrier_placed`, not only on the
    # turn a barrier happens to land.
    barriers = {(2, 3), (4, 3), (3, 4), (3, 2)}
    state = OwnGameState(position=(3, 3))
    for cell in barriers:
        state.record_barrier(cell)
    board = Board(size=7, barriers=barriers)
    assert evaluate_capture(state, board, [1, 1], barrier_placed=None) is True


def test_build_claim_response_echoes_claim_and_reports_caught_truthfully():
    assert build_claim_response([2, 5], caught=True) == {"claim": [2, 5], "caught": True}
    assert build_claim_response([2, 5], caught=False) == {"claim": [2, 5], "caught": False}
