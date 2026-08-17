"""interop/std_v1/capture.py tests (spec Section 5)."""

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.interop.std_v1.capture import build_claim_response, evaluate_capture


def test_condition_a_claim_co_location_is_a_capture():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    assert evaluate_capture(state, board, capture_claim=[3, 3], barrier_placed=None) is True


def test_no_capture_when_claim_misses_and_no_barrier():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    assert evaluate_capture(state, board, capture_claim=[0, 0], barrier_placed=None) is False


def test_condition_b_barrier_on_the_thief_is_a_capture():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    state.record_barrier((3, 3))  # caller applies the barrier before evaluating, per the contract
    assert evaluate_capture(state, board, capture_claim=[0, 0], barrier_placed=[3, 3]) is True


def test_condition_c_thief_trapped_is_a_capture():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(0, 0))
    # Wall in every orthogonal neighbor of the corner cell (0,0): (0,1) and (1,0).
    state.record_barrier((0, 1))
    state.record_barrier((1, 0))
    assert evaluate_capture(state, board, capture_claim=[6, 6], barrier_placed=[1, 0]) is True


def test_a_barrier_elsewhere_that_does_not_trap_is_not_a_capture():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    state.record_barrier((0, 0))
    assert evaluate_capture(state, board, capture_claim=[6, 6], barrier_placed=[0, 0]) is False


def test_build_claim_response_echoes_the_claim_and_is_truthful():
    assert build_claim_response([2, 3], caught=True) == {"claim": [2, 3], "caught": True}
    assert build_claim_response([2, 3], caught=False) == {"claim": [2, 3], "caught": False}
