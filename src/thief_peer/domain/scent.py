"""ScentField (PRD_4 §2.1, §3): stigmergic scent trail per the book's exact
Ch.4.3 formula, tau(t+1) = min(0.9, max(0, (1-rho)*tau(t) + delta_tau)) --
decay-then-add as one atomic step, never max-merge, capped at the book's
own reference centre intensity (also std_v1 interop guide Appendix E's
literal formula, cap = emit_intensity = 0.9). Rule 23 is [FATAL] on a
decay-formula deviation; an earlier draft of this module's spec got this
wrong by max-merging fresh deposits instead (see PRD_4 §4 for how that was
caught).
"""

from thief_peer.domain.board import Cell

# Figure 4's kernel, exactly as printed in the book (row_offset, col_offset)
# relative to the mover's own cell -> absolute intensity when
# pheromone_center_intensity == 0.9 (the book's own reference case).
_KERNEL_AT_REFERENCE_CENTER: dict[tuple[int, int], float] = {
    (-2, -2): 0.04, (-2, -1): 0.14, (-2, 0): 0.20, (-2, 1): 0.14, (-2, 2): 0.04,
    (-1, -2): 0.14, (-1, -1): 0.42, (-1, 0): 0.62, (-1, 1): 0.42, (-1, 2): 0.14,
    (0, -2): 0.20, (0, -1): 0.62, (0, 0): 0.90, (0, 1): 0.62, (0, 2): 0.20,
    (1, -2): 0.14, (1, -1): 0.42, (1, 0): 0.62, (1, 1): 0.42, (1, 2): 0.14,
    (2, -2): 0.04, (2, -1): 0.14, (2, 0): 0.20, (2, 1): 0.14, (2, 2): 0.04,
}  # fmt: skip
_REFERENCE_CENTER_INTENSITY = 0.90


class ScentField:
    def __init__(
        self,
        board_size: int,
        center_intensity: float = 0.9,
        decay_rate: float = 0.10,
    ):
        self._size = board_size
        self._decay_rate = decay_rate
        self._center_intensity = center_intensity
        scale = center_intensity / _REFERENCE_CENTER_INTENSITY
        self._kernel = {
            offset: value * scale for offset, value in _KERNEL_AT_REFERENCE_CENTER.items()
        }
        self._field: dict[Cell, float] = {}

    def advance(self, mover_cell: Cell) -> None:
        """One atomic step: decay every held cell by (1-rho), then add this
        turn's fixed kernel centered on mover_cell -- never two separate
        calls a caller could invoke out of order (PRD_4 §2.1, §4)."""
        decayed = {cell: intensity * (1 - self._decay_rate) for cell, intensity in self._field.items()}
        r, c = mover_cell
        for (dr, dc), delta in self._kernel.items():
            cell = (r + dr, c + dc)
            if not self._in_bounds(cell):
                continue
            decayed[cell] = decayed.get(cell, 0.0) + delta
        clamped = {
            cell: min(self._center_intensity, max(0.0, value)) for cell, value in decayed.items()
        }
        self._field = {cell: value for cell, value in clamped.items() if value > 0.0}

    def absorb(self, cells: dict[str, float]) -> None:
        """Overwrite (not merge) with an opponent's self-reported snapshot --
        it's already their own cumulative field, not a single fresh deposit
        (PRD_4 §4)."""
        self._field = {_cell_from_key(key): value for key, value in cells.items()}

    def snapshot(self) -> dict[str, float]:
        return {f"{r},{c}": value for (r, c), value in self._field.items() if value > 0.0}

    def _in_bounds(self, cell: Cell) -> bool:
        r, c = cell
        return 0 <= r < self._size and 0 <= c < self._size


def _cell_from_key(key: str) -> Cell:
    r, c = key.split(",")
    return int(r), int(c)
