"""ScentView (PRD_7 round 2): renders the currently-sensed opponent scent
snapshot as its own heatmap, deliberately a different hue from
`BoardView`'s belief heatmap (green vs. red/blue) so the two signals never
read as the same one on screen. Closes book ch.7.2's own three-item Local
Truth definition (own position, scent sensed, hints received) -- the Live
GUI previously only ever showed the first two.
"""

import tkinter as tk

_CANVAS_SIZE = 400


class ScentView:
    def __init__(self, parent: tk.Widget):
        self.canvas = tk.Canvas(parent, width=_CANVAS_SIZE, height=_CANVAS_SIZE, bg="white")
        self.canvas.pack(side=tk.LEFT)

    def render(self, view) -> None:
        self.canvas.delete("all")
        matrix = view.scent_matrix
        size = len(matrix)
        if size == 0:
            return

        cell = _CANVAS_SIZE / size
        max_p = max((p for row in matrix for p in row), default=0.0)
        for r, row in enumerate(matrix):
            for c, p in enumerate(row):
                self.canvas.create_rectangle(
                    c * cell,
                    r * cell,
                    (c + 1) * cell,
                    (r + 1) * cell,
                    fill=_scent_color(p, max_p),
                    outline="",
                )


def _scent_color(value: float, max_value: float) -> str:
    intensity = 0.0 if max_value <= 0 else min(value / max_value, 1.0)
    green = int(255 * intensity)
    return f"#00{green:02x}00"
