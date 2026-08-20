"""Capture evaluation for the std_v1 protocol's Thief role (spec Section
5). Reuses this repo's own already-tested domain/rules.py predicates
directly -- conditions A/B/C map exactly onto is_captured_by_landing /
is_captured_by_barrier / is_captured_by_stuck, the same functions the
native and cop_v1 protocols already use for the identical underlying
rule; only the wire format differs (JSON `[row, col]` arrays here,
translated to this repo's own `(row, col)` tuples at this boundary).

This module originally assumed `capture_claim` is present on *every* Cop
turn unconditionally -- true for every opponent seen live until a real
one (ali-ahm1) sent `null` instead, following the same "only claim when
confident, since a claim reveals my own position" convention a different
real opponent's own published research documents as their own police
brain's design. Section 9's own "Everything a peer sends is untrusted" is
the standing rule here regardless of what any one opponent's convention
turns out to be: a missing claim is "no claim was made this turn," not a
crash -- condition A (claim co-location) simply has nothing to check.
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
    capture_claim: list[int] | None,
    barrier_placed: list[int] | None,
) -> bool:
    """True if any of the spec's three terminal conditions (A/B/C) holds
    for this Cop turn. `barrier_placed`, when present, must already have
    been recorded into `state.known_barriers` by the caller before this
    runs -- condition C is defined as "after the declared barrier is
    applied". Condition A (claim co-location) only applies when
    `capture_claim` is actually present -- a real opponent that only
    claims when confident sends `null` on every other turn (see this
    module's own docstring); B/C are unaffected either way."""
    if capture_claim is not None:
        claim_cell: Cell = tuple(capture_claim)
        if is_captured_by_landing(state, claim_cell):
            return True
    if barrier_placed is not None:
        barrier_cell: Cell = tuple(barrier_placed)
        if is_captured_by_barrier(state, barrier_cell):
            return True
    # Condition C (rule 47, "no legal move") is a function of this side's
    # own *accumulated* known_barriers, not this turn's specific barrier --
    # a barrier placed on an earlier turn can box this side in on a later
    # turn where the Cop doesn't place a new one at all. Gating this check
    # on `barrier_placed is not None` (moamteam's own real find, cost them
    # a series) would silently skip that case forever, since nothing else
    # in this loop ever re-checks it.
    if is_captured_by_stuck(state, board):
        return True
    return False


def build_claim_response(capture_claim: list[int] | None, caught: bool) -> dict | None:
    """Spec Section 5: `claim_response = {"claim": [row, col], "caught":
    ...}`, set truthfully, echoing back the claim it's actually answering.
    Returns `None` when `capture_claim` itself is `None` -- there is
    nothing to answer when the Cop made no claim this turn (see this
    module's own docstring); the caller must not send a response to a
    claim that was never made."""
    if capture_claim is None:
        return None
    return {"claim": list(capture_claim), "caught": caught}
