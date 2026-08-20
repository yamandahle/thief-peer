"""BeliefGrid (PRD_4 §2.3, §3): a probability distribution over the
believed opponent position, updated from the opponent's scent field alone.
A hint is never folded in as a second observation here -- scent is
unfakeable ground truth, a hint is a claim to be tested against it, never
trusted standalone (book Ch.4.4/6.4; PRD_4 §4).

`observe_declaration` (PLAN.md Stage 7.4) is a second, separate evidence
channel: scent saturates flat late-game (confirmed live against a real
opponent -- every cell read ~0.18-0.21 by step 21, teaching the belief
nothing further), but the wire's own `capture_claim`/`barrier_placed`
fields state the sender's position outright every turn regardless. Kept as
its own method, not folded into `observe_scent`, because it's a different
kind of evidence (a stated fact, not a physical trace) and needs its own
trust floor rather than a plain multiplicative boost.
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

    def observe_declaration(self, cell: Cell, *, radius: int = 0, trust: float = 0.97) -> None:
        """Fold in a stated position (`capture_claim` -> radius 0, the
        sender claims to stand exactly there; `barrier_placed` -> radius 1,
        the barrier law only allows the placer's own cell or an orthogonal
        neighbor) as direct evidence. `trust` is the probability mass
        placed on the declared radius after this call; the remaining
        `1 - trust` stays spread (proportionally, not wiped) over every
        other cell, so a single false declaration -- the spec permits
        lying -- can never fully blind the belief."""
        r0, c0 = cell
        declared = {
            (r, c)
            for r in range(max(0, r0 - radius), min(self._size, r0 + radius + 1))
            for c in range(max(0, c0 - radius), min(self._size, c0 + radius + 1))
            if abs(r - r0) + abs(c - c0) <= radius
        }
        total_declared = sum(self._matrix[r][c] for r, c in declared)
        remaining = 1.0 - total_declared
        if total_declared <= 0.0 or remaining <= 0.0:
            return  # degenerate distribution -- nothing sane to reweight
        boost = trust / total_declared
        fade = (1.0 - trust) / remaining
        for r in range(self._size):
            for c in range(self._size):
                self._matrix[r][c] *= boost if (r, c) in declared else fade
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
