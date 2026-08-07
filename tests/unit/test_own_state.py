"""OwnGameState tests per PRD_1 §5: apply_move validates against
board.legal_moves before mutating anything (state unchanged on rejection),
visited/step_count update correctly, known_barriers only grows."""

import pytest

from thief_peer.constants import Direction
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.exceptions import SimulationError


def test_initial_state():
    state = OwnGameState(position=(3, 3))
    assert state.position == (3, 3)
    assert state.visited == set()
    assert state.known_barriers == set()
    assert state.step_count == 0


def test_apply_move_updates_position_visited_and_step_count():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    state.apply_move(Direction.N, board)
    assert state.position == (2, 3)
    assert state.visited == {(3, 3)}  # old position recorded
    assert state.step_count == 1


def test_apply_move_stay_keeps_position_but_still_counts_as_a_step():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    state.apply_move(None, board)
    assert state.position == (3, 3)
    assert state.visited == {(3, 3)}
    assert state.step_count == 1


def test_apply_move_sequence_accumulates_visited_and_step_count():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    for direction in [Direction.N, Direction.N, Direction.E, Direction.S, Direction.W]:
        state.apply_move(direction, board)
    assert state.step_count == 5
    assert state.position == (2, 3)  # net: N,N,E,S,W -> back to col 3, row 2
    assert (3, 3) in state.visited
    assert (1, 3) in state.visited


def test_apply_move_rejects_illegal_move_into_barrier_and_leaves_state_unchanged():
    board = Board(size=7, barriers={(2, 3)})
    state = OwnGameState(position=(3, 3))
    state.record_barrier((2, 3))
    with pytest.raises(SimulationError):
        state.apply_move(Direction.N, board)
    assert state.position == (3, 3)
    assert state.visited == set()
    assert state.step_count == 0


def test_apply_move_rejects_illegal_move_off_grid_and_leaves_state_unchanged():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(0, 0))
    with pytest.raises(SimulationError):
        state.apply_move(Direction.N, board)  # off-board from the corner
    assert state.position == (0, 0)
    assert state.step_count == 0


def test_record_barrier_adds_to_known_barriers():
    state = OwnGameState(position=(3, 3))
    state.record_barrier((1, 1))
    assert (1, 1) in state.known_barriers


def test_known_barriers_only_grows_never_shrinks():
    state = OwnGameState(position=(3, 3))
    state.record_barrier((1, 1))
    state.record_barrier((2, 2))
    state.record_barrier((1, 1))  # duplicate, set semantics — no error, no shrink
    assert state.known_barriers == {(1, 1), (2, 2)}
