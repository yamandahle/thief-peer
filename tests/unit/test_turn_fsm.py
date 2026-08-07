"""peer/turn_fsm.py tests (PRD_8 §2.4). The book's literal transition table
(Ch.8 p.63), extracted via pdftotext, not a paraphrase -- every edge in the
table must succeed, every non-edge must raise, and TECHNICAL_LOSS must be a
true terminal state with zero outbound transitions."""

import pytest

from thief_peer.exceptions import SimulationError
from thief_peer.peer.turn_fsm import TurnFsm

_ALL_STATES = [
    "WAITING_FOR_OPPONENT",
    "COMPUTING_MOVE",
    "COMMITTING",
    "AWAITING_REVEAL",
    "VERIFYING",
    "TECHNICAL_LOSS",
]

_LEGAL_EDGES = [
    ("WAITING_FOR_OPPONENT", "COMPUTING_MOVE"),
    ("COMPUTING_MOVE", "COMMITTING"),
    ("COMPUTING_MOVE", "TECHNICAL_LOSS"),
    ("COMMITTING", "AWAITING_REVEAL"),
    ("AWAITING_REVEAL", "VERIFYING"),
    ("AWAITING_REVEAL", "TECHNICAL_LOSS"),
    ("VERIFYING", "WAITING_FOR_OPPONENT"),
]


def test_starts_in_waiting_for_opponent():
    assert TurnFsm().state == "WAITING_FOR_OPPONENT"


@pytest.mark.parametrize("from_state,to_state", _LEGAL_EDGES)
def test_every_legal_edge_in_the_books_table_succeeds(from_state, to_state):
    fsm = TurnFsm()
    fsm._state = from_state  # jump directly to the state under test

    fsm.transition(to_state)

    assert fsm.state == to_state


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        (from_state, to_state)
        for from_state in _ALL_STATES
        for to_state in _ALL_STATES
        if (from_state, to_state) not in _LEGAL_EDGES
    ],
)
def test_every_non_edge_is_rejected(from_state, to_state):
    fsm = TurnFsm()
    fsm._state = from_state

    with pytest.raises(SimulationError, match="Illegal transition"):
        fsm.transition(to_state)

    assert fsm.state == from_state  # rejected transition leaves state unchanged


def test_technical_loss_is_a_true_terminal_state():
    fsm = TurnFsm()
    fsm._state = "TECHNICAL_LOSS"

    for target in _ALL_STATES:
        with pytest.raises(SimulationError):
            fsm.transition(target)


def test_a_full_round_loop_matches_the_books_cycle():
    fsm = TurnFsm()

    fsm.transition("COMPUTING_MOVE")
    fsm.transition("COMMITTING")
    fsm.transition("AWAITING_REVEAL")
    fsm.transition("VERIFYING")
    fsm.transition("WAITING_FOR_OPPONENT")

    assert fsm.state == "WAITING_FOR_OPPONENT"
