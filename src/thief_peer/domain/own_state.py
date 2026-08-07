"""This peer's own mutable game state — position, trail, learned barriers,
step count. Legality is always checked against `known_barriers` (this
peer's own knowledge), not the Board's fixed construction-time snapshot
(PRD_1 §4)."""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board, Cell
from thief_peer.exceptions import SimulationError


class OwnGameState:
    def __init__(self, position: Cell):
        self.position: Cell = position
        self.visited: set[Cell] = set()
        self.known_barriers: set[Cell] = set()
        self.step_count: int = 0

    def apply_move(self, direction: Direction | None, board: Board) -> None:
        """Validate first, mutate only on success — an illegal move must
        leave state byte-for-byte unchanged (PRD_1 §5)."""
        legal = board.legal_moves(self.position, frozenset(self.known_barriers))
        matches = [cell for d, cell in legal if d == direction]
        if not matches:
            raise SimulationError(
                f"Illegal move: {direction} from {self.position}"
            )
        old_position = self.position
        self.visited.add(old_position)
        self.position = matches[0]
        self.step_count += 1

    def record_barrier(self, cell: Cell) -> None:
        self.known_barriers.add(cell)
