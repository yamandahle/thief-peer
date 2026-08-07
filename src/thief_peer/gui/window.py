"""PeerWindow (PRD_7 §2.1-2.2, §3; PLAN.md ADR-8): Tkinter root that renders
only fields present in the view object passed to it. `PeerView` is the
exact shape `PeerRuntime.view()` (arriving in a later stage) is expected to
produce -- it structurally cannot carry an opponent position, since no such
field exists on it at all. Partial observability is enforced at the type
level here, not by GUI-drawing convention.
"""

import tkinter as tk
from dataclasses import dataclass

from thief_peer.gui.board_view import BoardView
from thief_peer.gui.turn_banner import TurnBanner


@dataclass(frozen=True)
class PeerView:
    own_position: tuple[int, int]
    belief_matrix: list[list[float]]
    turn_state: str
    step_count: int


class PeerWindow:
    def __init__(self, root: tk.Tk | None = None):
        self.root = root or tk.Tk()
        self.root.title("Thief Peer")
        self.turn_banner = TurnBanner(self.root)
        self.board_view = BoardView(self.root)

    def render(self, view: PeerView) -> None:
        self.board_view.render(view)
        self.turn_banner.render(view.turn_state)

    def run(self) -> None:
        self.root.mainloop()
