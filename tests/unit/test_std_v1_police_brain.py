"""interop/std_v1/police_brain.py tests: the minimal greedy pursuit used
only on std_v1's own alternated (Police-role) sub-games."""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board
from thief_peer.interop.std_v1.police_brain import believed_thief_cell, choose_police_move


def test_believed_thief_cell_returns_fallback_when_scent_is_empty():
    assert believed_thief_cell({}, fallback=(3, 3)) == (3, 3)


def test_believed_thief_cell_returns_the_highest_intensity_cell():
    scent = {"1,1": 0.2, "4,5": 0.9, "0,0": 0.5}
    assert believed_thief_cell(scent, fallback=(3, 3)) == (4, 5)


def test_choose_police_move_heads_toward_the_target():
    board = Board(size=7, barriers=set())
    direction = choose_police_move(board, position=(0, 0), known_barriers=frozenset(), target=(0, 5))
    assert direction == Direction.E


def test_choose_police_move_returns_none_when_already_at_target():
    board = Board(size=7, barriers=set())
    direction = choose_police_move(board, position=(3, 3), known_barriers=frozenset(), target=(3, 3))
    assert direction is None


def test_choose_police_move_never_picks_a_barrier_blocked_direction():
    board = Board(size=7, barriers={(0, 1)})
    direction = choose_police_move(board, position=(0, 0), known_barriers=frozenset({(0, 1)}), target=(0, 5))
    assert direction != Direction.E
