"""TurnFsm (PRD_8 §2.4; PLAN.md ADR-2): the book's turn state machine,
copied byte-for-byte from its literal Python transition table (Ch.8 p.63,
extracted via pdftotext) rather than a paraphrase. In a fully decentralized
2-peer game there is no referee to catch a desync; illegal transitions raise
immediately instead of silently overwriting state -- this is the book's
primary defense against deadlock.
"""

from thief_peer.exceptions import SimulationError

TRANSITIONS: dict[str, set[str]] = {
    "WAITING_FOR_OPPONENT": {"COMPUTING_MOVE"},
    "COMPUTING_MOVE": {"COMMITTING", "TECHNICAL_LOSS"},
    "COMMITTING": {"AWAITING_REVEAL"},
    "AWAITING_REVEAL": {"VERIFYING", "TECHNICAL_LOSS"},
    "VERIFYING": {"WAITING_FOR_OPPONENT"},
    "TECHNICAL_LOSS": set(),  # terminal
}


class TurnFsm:
    def __init__(self):
        self._state = "WAITING_FOR_OPPONENT"

    @property
    def state(self) -> str:
        return self._state

    def transition(self, target: str) -> None:
        if target not in TRANSITIONS[self._state]:
            raise SimulationError(f"Illegal transition: {self._state} -> {target}")
        self._state = target
