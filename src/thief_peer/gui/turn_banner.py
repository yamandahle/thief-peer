"""TurnBanner (PRD_7 §2.2, §3): a visual manifestation of the turn FSM
(`PLAN.md` ADR-2) -- green "YOUR TURN" only during `COMPUTING_MOVE`, grey
"LOCKED" for every other state, from the moment our Commit is sent until
the opponent's turn completes. Not decorative -- the visible proof the
state machine is preventing acting out of turn.
"""

import tkinter as tk

_COLOR_YOUR_TURN = "#2ecc71"
_COLOR_LOCKED = "#95a5a6"


class TurnBanner:
    def __init__(self, parent: tk.Widget):
        self.label = tk.Label(parent, text="", font=("Arial", 16, "bold"))
        self.label.pack()

    def render(self, turn_state: str) -> None:
        text, color = banner_for_state(turn_state)
        self.label.config(text=text, bg=color)


def banner_for_state(turn_state: str) -> tuple[str, str]:
    if turn_state == "COMPUTING_MOVE":
        return "YOUR TURN", _COLOR_YOUR_TURN
    return "LOCKED", _COLOR_LOCKED
