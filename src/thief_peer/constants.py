"""Project-wide constants. Direction is an Enum (not a config-driven list)
so the constant no-diagonals move-set rule (book Appendix ו) is a type
error to violate, not just a config mistake — see PRD_1_base_logic.md §4.
"""

from enum import Enum


class Direction(Enum):
    N = "N"
    S = "S"
    E = "E"
    W = "W"


class MoveType(Enum):
    MOVE = "MOVE"
    HOLD = "HOLD"


# (dr, dc) offset per direction, top-left origin, row increases downward —
# matches the book's default axis_origin_corner/axis_start_index (Ch.3).
DELTAS: dict[Direction, tuple[int, int]] = {
    Direction.N: (-1, 0),
    Direction.S: (1, 0),
    Direction.E: (0, 1),
    Direction.W: (0, -1),
}

# Reserved for Stage 6 (Commit-Reveal): secrets.token_hex(NONCE_BYTES).
NONCE_BYTES = 16
