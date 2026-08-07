"""Board tests, mirroring PRD_1_base_logic.md §5's acceptance criteria
exactly (corner=3 moves+STAY, center=4 moves+STAY, Manhattan not
Euclidean distance, barrier removes exactly one direction)."""

import pytest

from thief_peer.constants import Direction
from thief_peer.domain.board import Board
from thief_peer.exceptions import SimulationError


def test_rejects_non_positive_size():
    with pytest.raises(SimulationError):
        Board(size=0, barriers=set())


def test_barriers_are_stored_as_immutable_frozenset():
    board = Board(size=7, barriers={(1, 1)})
    assert isinstance(board.barriers, frozenset)
    assert board.barriers == frozenset({(1, 1)})


def test_in_bounds():
    board = Board(size=7, barriers=set())
    assert board.in_bounds((0, 0))
    assert board.in_bounds((6, 6))
    assert not board.in_bounds((7, 0))
    assert not board.in_bounds((0, -1))


def test_is_barrier():
    board = Board(size=7, barriers={(2, 2)})
    assert board.is_barrier((2, 2))
    assert not board.is_barrier((2, 3))


def test_legal_moves_at_corner_has_two_directions_plus_stay():
    board = Board(size=7, barriers=set())
    moves = board.legal_moves((0, 0), board.barriers)
    directions = {d for d, _ in moves if d is not None}
    # corner (0,0): N and W are off-board, only S/E remain.
    assert directions == {Direction.S, Direction.E}
    assert any(d is None for d, cell in moves if cell == (0, 0))
    assert len(moves) == 3  # S, E, STAY


def test_legal_moves_at_center_has_four_directions_plus_stay():
    board = Board(size=7, barriers=set())
    moves = board.legal_moves((3, 3), board.barriers)
    directions = {d for d, _ in moves if d is not None}
    assert directions == {Direction.N, Direction.S, Direction.E, Direction.W}
    assert len(moves) == 5  # N, S, E, W, STAY


def test_legal_moves_always_includes_stay_even_when_fully_boxed():
    # Thief at (3,3) surrounded on all four sides by barriers.
    barriers = {(2, 3), (4, 3), (3, 2), (3, 4)}
    board = Board(size=7, barriers=barriers)
    moves = board.legal_moves((3, 3), board.barriers)
    assert moves == [(None, (3, 3))]


def test_legal_moves_excludes_only_the_barrier_direction():
    board = Board(size=7, barriers={(2, 3)})  # barrier north of (3,3)
    moves = board.legal_moves((3, 3), board.barriers)
    directions = {d for d, _ in moves if d is not None}
    assert directions == {Direction.S, Direction.E, Direction.W}
    assert Direction.N not in directions


def test_legal_moves_uses_the_passed_barriers_not_the_boards_own():
    # Board constructed with no barriers, but caller passes a different
    # (e.g. OwnGameState.known_barriers) set — legal_moves must honor it.
    board = Board(size=7, barriers=set())
    moves = board.legal_moves((3, 3), frozenset({(2, 3)}))
    directions = {d for d, _ in moves if d is not None}
    assert Direction.N not in directions


def test_distance_is_manhattan_not_euclidean():
    board = Board(size=7, barriers=set())
    assert board.distance((0, 0), (3, 4)) == 7  # not 5 (Euclidean-ish)
