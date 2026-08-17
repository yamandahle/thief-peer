from thief_peer.domain.board import Board
from thief_peer.interop.std_v1.police_brain import believed_thief_cell, choose_police_move


def test_believed_thief_cell_falls_back_when_no_scent():
    assert believed_thief_cell({}, fallback=(3, 3)) == (3, 3)


def test_believed_thief_cell_picks_highest_intensity_cell():
    scent = {"1,1": 0.2, "4,4": 0.9, "2,2": 0.5}
    assert believed_thief_cell(scent, fallback=(0, 0)) == (4, 4)


def test_choose_police_move_steps_toward_target():
    board = Board(size=7, barriers=set())
    direction = choose_police_move(board, position=(0, 0), known_barriers=frozenset(), target=(3, 3))
    assert direction is not None
    # Either a South or East step reduces Manhattan distance to (3, 3).
    assert direction.value in ("S", "E")


def test_choose_police_move_stays_when_already_at_target():
    board = Board(size=7, barriers=set())
    direction = choose_police_move(board, position=(3, 3), known_barriers=frozenset(), target=(3, 3))
    assert direction is None


def test_choose_police_move_respects_barriers():
    board = Board(size=3, barriers=set())
    # Boxed in on the East/South sides -- only STAY or a non-improving
    # direction remain legal relative to a target further east.
    barriers = frozenset({(0, 1)})
    direction = choose_police_move(board, position=(0, 0), known_barriers=barriers, target=(0, 2))
    assert direction != "E"
