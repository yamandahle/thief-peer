"""PeerWindow (PRD_7 §2.1-2.2, §3; PLAN.md ADR-8): Tkinter root that renders
only fields present in the view object passed to it. `PeerView` is the
exact shape `PeerRuntime.view()` (arriving in a later stage) is expected to
produce -- it structurally cannot carry an opponent position, since no such
field exists on it at all. Partial observability is enforced at the type
level here, not by GUI-drawing convention.

`scent_matrix`/`hint_text` (PRD_7 round 2) close the rest of book ch.7.2's
own three-item Local Truth definition -- own position, scent currently
sensed, hints received -- this window previously only ever showed the
first two. Both stay local-truth-safe by the same structural argument as
`own_position`/`belief_matrix`: `scent_matrix` is this side's own received
scent snapshot (already-local data, not the opponent's true position) and
`hint_text` is verbal text this side actually received, same category.
Defaulted (not required) so every existing `PeerView(...)` call site that
predates this doesn't need updating just to keep constructing one.
"""

import tkinter as tk
from dataclasses import dataclass, field

from thief_peer.gui.board_view import BoardView
from thief_peer.gui.scent_view import ScentView
from thief_peer.gui.turn_banner import TurnBanner


@dataclass(frozen=True)
class PeerView:
    own_position: tuple[int, int]
    belief_matrix: list[list[float]]
    turn_state: str
    step_count: int
    scent_matrix: list[list[float]] = field(default_factory=list)
    hint_text: str = ""


class PeerWindow:
    def __init__(self, root: tk.Tk | None = None):
        self.root = root or tk.Tk()
        self.root.title("Thief Peer")
        self.turn_banner = TurnBanner(self.root)
        heatmaps = tk.Frame(self.root)
        heatmaps.pack()
        self.board_view = BoardView(heatmaps)
        self.scent_view = ScentView(heatmaps)
        self.hint_label = tk.Label(self.root, text="", font=("Arial", 10))
        self.hint_label.pack()

    def render(self, view: PeerView) -> None:
        self.board_view.render(view)
        self.scent_view.render(view)
        self.turn_banner.render(view.turn_state)
        self.hint_label.config(
            text=f"Opponent hint: {view.hint_text}" if view.hint_text else ""
        )

    def run(self) -> None:
        self.root.mainloop()
