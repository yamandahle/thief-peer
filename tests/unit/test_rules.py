"""Capture/survival rules — pure functions of (board, own_state, config),
per PRD_1 §5. is_captured_by_stuck implements the resolved reading of the
"stuck = captured" rule (PRD_1 §4 / PRD_6 §2.6): no legal MOVE remains,
only STAY — this is now the final, locked-in interpretation, not open."""

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.rules import (
    has_survived,
    is_captured_by_barrier,
    is_captured_by_stuck,
)


def test_is_captured_by_barrier_true_only_on_current_cell():
    state = OwnGameState(position=(3, 3))
    assert is_captured_by_barrier(state, (3, 3)) is True


def test_is_captured_by_barrier_false_on_adjacent_cell():
    state = OwnGameState(position=(3, 3))
    assert is_captured_by_barrier(state, (2, 3)) is False


def test_is_captured_by_stuck_false_when_at_least_one_move_exists():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    assert is_captured_by_stuck(state, board) is False


def test_is_captured_by_stuck_true_when_fully_boxed_by_barriers():
    barriers = {(2, 3), (4, 3), (3, 2), (3, 4)}
    board = Board(size=7, barriers=barriers)
    state = OwnGameState(position=(3, 3))
    for cell in barriers:
        state.record_barrier(cell)
    assert is_captured_by_stuck(state, board) is True


def test_is_captured_by_stuck_true_when_boxed_by_board_edges_and_barriers():
    # Corner (0,0): N/W are off-board; wall S and E too -> only STAY remains.
    barriers = {(1, 0), (0, 1)}
    board = Board(size=7, barriers=barriers)
    state = OwnGameState(position=(0, 0))
    for cell in barriers:
        state.record_barrier(cell)
    assert is_captured_by_stuck(state, board) is True


def test_has_survived_false_one_step_before_threshold():
    state = OwnGameState(position=(3, 3))
    state.step_count = 34
    assert has_survived(state, survival_threshold=35) is False


def test_has_survived_true_at_threshold():
    state = OwnGameState(position=(3, 3))
    state.step_count = 35
    assert has_survived(state, survival_threshold=35) is True
