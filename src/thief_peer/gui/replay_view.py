"""ReplayView (PRD_7 §2.3, §3): the mandatory, unforgeable witness. Steps
through a saved match log and re-verifies the Commit-Reveal chain live, per
step, using the *exact same* `domain/crypto.py` functions built in Stage 6
-- never a separate/duplicated verification routine. Any mismatch, even a
single-byte change to past data, flips the whole match to TAMPERED with no
appeal -- the decision is made by SHA-256's collision resistance, not human
judgment.
"""

import tkinter as tk

from thief_peer.domain.crypto import CommitReveal

_VERIFIED_OK = "Verified OK"
_TAMPERED = "TAMPERED"
_COLOR_OK = "#2ecc71"
_COLOR_TAMPERED = "#e74c3c"


def verify_step(entry: dict) -> str:
    payload = entry["payload"]
    nonce = payload["nonce"]
    content = {key: value for key, value in payload.items() if key != "nonce"}
    if CommitReveal.verify(content, nonce, entry["commit"]):
        return _VERIFIED_OK
    return _TAMPERED


def replay(log: list[dict]) -> str:
    for entry in log:
        if verify_step(entry) == _TAMPERED:
            return _TAMPERED
    return _VERIFIED_OK


class ReplayView:
    def __init__(self, parent: tk.Widget, log: list[dict]):
        self.log = log
        self.index = 0
        self.label = tk.Label(parent, text="", font=("Arial", 16, "bold"))
        self.label.pack()
        self._render_current()

    def step_forward(self) -> None:
        if self.index < len(self.log) - 1:
            self.index += 1
        self._render_current()

    def step_back(self) -> None:
        if self.index > 0:
            self.index -= 1
        self._render_current()

    def _render_current(self) -> None:
        if not self.log:
            self.label.config(text="(empty log)")
            return
        status = verify_step(self.log[self.index])
        color = _COLOR_OK if status == _VERIFIED_OK else _COLOR_TAMPERED
        self.label.config(text=f"Step {self.index}: {status}", bg=color)
