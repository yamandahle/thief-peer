"""Pins the constant move-set rule at the type level (PRD_1 §4: no diagonals,
ever, not even by mutual agreement) — a missing/extra Direction member is a
test failure, not a silent config drift."""

from thief_peer.constants import DELTAS, Direction, MoveType


def test_direction_has_exactly_four_orthogonal_members():
    assert {d.name for d in Direction} == {"N", "S", "E", "W"}


def test_deltas_covers_every_direction_with_orthogonal_offsets():
    assert set(DELTAS.keys()) == set(Direction)
    # Exactly one axis moves per direction — never a diagonal (dr, dc) pair.
    for direction, (dr, dc) in DELTAS.items():
        assert (dr, dc) in {(-1, 0), (1, 0), (0, -1), (0, 1)}, direction


def test_deltas_are_consistent_with_top_left_origin_convention():
    # top-left origin, row increases downward: N decreases row, S increases it.
    assert DELTAS[Direction.N] == (-1, 0)
    assert DELTAS[Direction.S] == (1, 0)
    assert DELTAS[Direction.W] == (0, -1)
    assert DELTAS[Direction.E] == (0, 1)


def test_move_type_has_move_and_hold_only():
    # Thief never places a barrier (Cop-only mechanic) — no BARRIER member.
    assert {m.name for m in MoveType} == {"MOVE", "HOLD"}
