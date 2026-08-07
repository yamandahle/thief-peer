"""Discrete grid geometry — pure, no I/O, no network (PRD_1 §1).
Immutable per sub-game snapshot; new barrier knowledge is tracked
separately on OwnGameState, never mutated here (PRD_1 §4)."""

from thief_peer.constants import DELTAS, Direction
from thief_peer.exceptions import SimulationError

Cell = tuple[int, int]


class Board:
    def __init__(self, size: int, barriers: set[Cell]):
        if size <= 0:
            raise SimulationError(f"Board size must be positive, got {size}")
        self.size = size
        self.barriers: frozenset[Cell] = frozenset(barriers)

    def in_bounds(self, cell: Cell) -> bool:
        r, c = cell
        return 0 <= r < self.size and 0 <= c < self.size

    def is_barrier(self, cell: Cell) -> bool:
        return cell in self.barriers

    def legal_moves(
        self, position: Cell, barriers: frozenset[Cell]
    ) -> list[tuple[Direction | None, Cell]]:
        """STAY is represented as (None, position) — always present, even
        when every orthogonal direction is blocked (PRD_1 §2.2/§5)."""
        moves: list[tuple[Direction | None, Cell]] = []
        r, c = position
        for direction, (dr, dc) in DELTAS.items():
            target = (r + dr, c + dc)
            if self.in_bounds(target) and target not in barriers:
                moves.append((direction, target))
        moves.append((None, position))
        return moves

    def distance(self, a: Cell, b: Cell) -> int:
        """Manhattan distance — the true minimum step count under this
        orthogonal-only move set (admissible heuristic, PRD_1 §3)."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
