"""Capture evaluation for the std_v1 protocol's Thief role (spec Section
5). Reuses this repo's own already-tested domain/rules.py predicates
directly -- conditions A/B/C map exactly onto is_captured_by_landing /
is_captured_by_barrier / is_captured_by_stuck, the same functions the
native and cop_v1 protocols already use for the identical underlying
rule; only the wire format differs (JSON `[row, col]` arrays here,
translated to this repo's own `(row, col)` tuples at this boundary).

The Cop declares `capture_claim` on *every* Cop turn, unconditionally
(Section 5, "with no gating") -- so a Thief playing this protocol answers
every single Cop turn with a `claim_response`, not just the one turn a
real capture happens on; `caught` is `false` on all but (at most) the
final one.
"""

from __future__ import annotations

from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.rules import (
    is_captured_by_barrier,
    is_captured_by_landing,
    is_captured_by_stuck,
)


def evaluate_capture(
    state: OwnGameState,
    board: Board,
    capture_claim: list[int],
    barrier_placed: list[int] | None,
) -> bool:
    """True if any of the spec's three terminal conditions (A/B/C) holds
    for this Cop turn. `barrier_placed`, when present, must already have
    been recorded into `state.known_barriers` by the caller before this
    runs -- condition C is defined as "after the declared barrier is
    applied". Condition A (claim co-location) is always checked, since
    `capture_claim` is always present; B/C only apply on a barrier turn."""
    claim_cell: Cell = tuple(capture_claim)
    if is_captured_by_landing(state, claim_cell):
        return True
    if barrier_placed is not None:
        barrier_cell: Cell = tuple(barrier_placed)
        if is_captured_by_barrier(state, barrier_cell):
            return True
        if is_captured_by_stuck(state, board):
            return True
    return False


def build_claim_response(capture_claim: list[int], caught: bool) -> dict:
    """Spec Section 5: `claim_response = {"claim": [row, col], "caught":
    ...}`, set truthfully. `capture_claim` is echoed back -- it is the
    field that's actually named "the claim", and (unlike `barrier_placed`)
    it is present on every Cop turn, so there is always something to
    answer once the first Cop turn has arrived."""
    return {"claim": list(capture_claim), "caught": caught}
