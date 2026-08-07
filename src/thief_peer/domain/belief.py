"""BeliefGrid (PRD_4 §2.3, §3): a probability distribution over the
believed opponent position, updated from the opponent's scent field alone.
A hint is never folded in as a second observation here -- scent is
unfakeable ground truth, a hint is a claim to be tested against it, never
trusted standalone (book Ch.4.4/6.4; PRD_4 §4).
"""

from thief_peer.constants import DELTAS
from thief_peer.domain.board import Cell


class BeliefGrid:
    def __init__(self, board_size: int):
        self._size = board_size
        uniform = 1.0 / (board_size * board_size)
        self._matrix = [[uniform] * board_size for _ in range(board_size)]

    def observe_scent(self, cells: dict[str, float]) -> None:
        """Bayesian-style reweighting: scale each cell's probability by
        (1 + intensity) -- full trust in the physical, unfakeable signal --
        then renormalize (PRD_4 §2.3/§3)."""
        for r in range(self._size):
            for c in range(self._size):
                intensity = cells.get(f"{r},{c}", 0.0)
                self._matrix[r][c] *= 1.0 + intensity
        self._normalize()

    def diffuse(self) -> None:
        """Spread each cell's mass evenly across its own legal-move
        neighborhood (one opponent move happened, direction unknown)."""
        spread = [[0.0] * self._size for _ in range(self._size)]
        for r in range(self._size):
            for c in range(self._size):
                mass = self._matrix[r][c]
                if mass == 0.0:
                    continue
                neighbors: list[Cell] = [(r, c)]  # STAY is always legal
                for dr, dc in DELTAS.values():
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self._size and 0 <= nc < self._size:
                        neighbors.append((nr, nc))
                share = mass / len(neighbors)
                for nr, nc in neighbors:
                    spread[nr][nc] += share
        self._matrix = spread
        self._normalize()

    def most_likely(self) -> Cell:
        best_cell, best_p = (0, 0), -1.0
        for r in range(self._size):
            for c in range(self._size):
                if self._matrix[r][c] > best_p:
                    best_cell, best_p = (r, c), self._matrix[r][c]
        return best_cell

    def as_matrix(self) -> list[list[float]]:
        return self._matrix

    def _normalize(self) -> None:
        total = sum(sum(row) for row in self._matrix)
        self._matrix = [[value / total for value in row] for row in self._matrix]
