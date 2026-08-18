"""ReplayView (PRD_7 §2.3, §3): the mandatory, unforgeable witness. Steps
through a saved match log and re-verifies the Commit-Reveal chain live, per
step, using the *exact same* verification routine each protocol's own live
play already used -- never a separate/duplicated one. Any mismatch, even a
single-byte change to past data, flips the whole match to TAMPERED with no
appeal -- the decision is made by SHA-256's collision resistance, not human
judgment.

Two protocols, two incompatible commit-reveal schemes: `domain/crypto.py::
CommitReveal` (native/cop_v1) embeds the nonce inside the hashed JSON
object; `interop/std_v1/crypto.py::commit_of` (std_v1) hashes
canonical(payload) + "|" + nonce as a plain string instead (see that
module's own docstring). A log's `"protocol"` field (`report/artifacts.py::
build_log`, defaulting to "native" for every existing caller) selects which
one verifies it -- reusing either scheme for the other protocol's records
would silently "verify" against the wrong bytes.
"""

import tkinter as tk

from thief_peer.domain.crypto import CommitReveal
from thief_peer.interop.std_v1 import replay_log as std_v1_replay_log

_VERIFIED_OK = "Verified OK"
_TAMPERED = "TAMPERED"
_COLOR_OK = "#2ecc71"
_COLOR_TAMPERED = "#e74c3c"


def verify_step(entry: dict, protocol: str = "native") -> str:
    if protocol == "std_v1":
        return std_v1_replay_log.verify_step(entry)
    payload = entry["payload"]
    nonce = payload["nonce"]
    content = {key: value for key, value in payload.items() if key != "nonce"}
    if CommitReveal.verify(content, nonce, entry["commit"]):
        return _VERIFIED_OK
    return _TAMPERED


def replay(log: list[dict], protocol: str = "native") -> str:
    for entry in log:
        if verify_step(entry, protocol) == _TAMPERED:
            return _TAMPERED
    return _VERIFIED_OK


class ReplayView:
    def __init__(self, parent: tk.Widget, log: list[dict], protocol: str = "native"):
        self.log = log
        self.protocol = protocol
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
        status = verify_step(self.log[self.index], self.protocol)
        color = _COLOR_OK if status == _VERIFIED_OK else _COLOR_TAMPERED
        self.label.config(text=f"Step {self.index}: {status}", bg=color)
