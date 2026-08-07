"""BoardView (PRD_7 §2.1-2.2, §3): renders the peer's own true position
(certain, drawn as a dot) plus the belief heatmap (`BeliefGrid.as_matrix()`,
Stage 4) as a cold-to-warm color gradient -- never the opponent's true
position, which `PeerView` structurally cannot carry (PLAN.md ADR-8).
"""

import tkinter as tk

_CANVAS_SIZE = 400


class BoardView:
    def __init__(self, parent: tk.Widget):
        self.canvas = tk.Canvas(parent, width=_CANVAS_SIZE, height=_CANVAS_SIZE, bg="white")
        self.canvas.pack()

    def render(self, view) -> None:
        self.canvas.delete("all")
        matrix = view.belief_matrix
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
                    fill=_heat_color(p, max_p),
                    outline="",
                )

        own_r, own_c = view.own_position
        margin = cell * 0.15
        self.canvas.create_oval(
            own_c * cell + margin,
            own_r * cell + margin,
            (own_c + 1) * cell - margin,
            (own_r + 1) * cell - margin,
            fill="black",
        )


def _heat_color(value: float, max_value: float) -> str:
    intensity = 0.0 if max_value <= 0 else min(value / max_value, 1.0)
    red = int(255 * intensity)
    blue = int(255 * (1 - intensity))
    return f"#{red:02x}00{blue:02x}"
