"""Minimal Police-role move chooser for std_v1 role alternation (spec
Section 6: sub-games 2/4/6 flip this repo into the opposite of its
natural Thief role). Deliberately a simple greedy pursuit -- legal and
spec-compliant, not a second real strategy investment; this repo's own
strategy work (PRD_3) is entirely on the Thief side. Never reached
outside std_v1's own alternated sub-games.
"""

from __future__ import annotations

from thief_peer.constants import Direction
from thief_peer.domain.board import Board, Cell


def believed_thief_cell(scent: dict[str, float], fallback: Cell) -> Cell:
    """The highest-intensity reported cell in the Thief's own last
    `smell_grid`, or `fallback` (the terms' own public `thief_start`)
    before anything has been sensed yet."""
    if not scent:
        return fallback
    key = max(scent, key=scent.get)
    r, c = key.split(",")
    return int(r), int(c)


def choose_police_move(
    board: Board, position: Cell, known_barriers: frozenset[Cell], target: Cell
) -> Direction | None:
    """Greedy: the legal move that most reduces Manhattan distance to
    `target`; STAY (None) once already there or when nothing improves on
    staying put."""
    best_direction: Direction | None = None
    best_distance = board.distance(position, target)
    for direction, cell in board.legal_moves(position, known_barriers):
        if direction is None:
            continue
        distance = board.distance(cell, target)
        if distance < best_distance:
            best_distance = distance
            best_direction = direction
    return best_direction
