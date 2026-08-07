"""Capture/survival rules (book Ch.3, Appendix ה). Pure functions of
(board, own_state, config) — no I/O, no network, trivially unit-testable.

"stuck = captured" resolution (PRD_1 §4 / PRD_6 §2.6, CLOSED, not open):
STAY is always technically legal, so a literal "zero legal actions" reading
is vacuous. Our locked-in reading: stuck means no legal MOVE direction
remains, only STAY.
"""

from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState


def is_captured_by_barrier(state: OwnGameState, new_barrier_cell: Cell) -> bool:
    return new_barrier_cell == state.position


def is_captured_by_stuck(state: OwnGameState, board: Board) -> bool:
    legal = board.legal_moves(state.position, frozenset(state.known_barriers))
    return all(direction is None for direction, _cell in legal)


def has_survived(state: OwnGameState, survival_threshold: int) -> bool:
    return state.step_count >= survival_threshold
