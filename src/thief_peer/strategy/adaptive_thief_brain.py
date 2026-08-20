"""AdaptiveThiefBrain (PLAN.md Stage 7.4): pessimistic one-ply evasion,
replacing `ThiefBrain`'s reactive current-square scoring. Selectable via
`[strategy] thief_class =
"thief_peer.strategy.adaptive_thief_brain:AdaptiveThiefBrain"` -- the
existing dotted-path `resolve_brain` switch (`strategy/brain_base.py`), so
this ships alongside `ThiefBrain` rather than replacing the default.

Why: `ThiefBrain` (`fleeing_brain.py`) scores each candidate cell against
the belief distribution *as it stands right now* -- it never asks what the
Cop could do in reply, including a Cop that places a barrier. A brain that
only reacts to the present is exactly what a Cop with any real lookahead
runs straight through. This brain instead scores each candidate by the
Cop's *best* plausible reply (pessimistic, not average), with an explicit
large danger penalty inside a 1-cell radius, mirroring the danger-override
principle a purely-averaged score can't express (a small chance of capture
next turn should dominate the decision, not get diluted into an average).

Non-determinism (PLAN.md Stage 7.2b): candidates within `_TIE_MARGIN` of
the best score are sampled via softmax rather than a fixed tie-break, so
behaviour isn't perfectly repeatable match to match. This is move-selection
randomness only, drawn from `self._rng` (a plain `random.Random`) -- never
the commit-reveal nonce, which stays `secrets`-based and is never touched
by this class.
"""

from __future__ import annotations

import math
import random

from thief_peer.constants import Direction
from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.brain_base import BrainBase

_TIE_MARGIN = 1e-6
_SOFTMAX_TEMPERATURE = 0.75
_DANGER_RADIUS = 1
_DANGER_PENALTY = 1000.0
_DISTANCE_WEIGHT = 1.0
_MOBILITY_WEIGHT = 1.5
_RECENCY_WEIGHT = 0.01  # small nudge only -- breaks true ties, never the primary signal


class AdaptiveThiefBrain(BrainBase):
    def __init__(
        self,
        *,
        danger_penalty: float = _DANGER_PENALTY,
        mobility_weight: float = _MOBILITY_WEIGHT,
        distance_weight: float = _DISTANCE_WEIGHT,
        rng: random.Random | None = None,
    ) -> None:
        self._danger_penalty = danger_penalty
        self._mobility_weight = mobility_weight
        self._distance_weight = distance_weight
        self._rng = rng or random.Random()
        self._last_visited_turn: dict[Cell, int] = {}
        self._turn = 0

    def _cop_pessimistic_replies(self, belief, board: Board) -> list[Cell]:
        """Every cell the Cop could plausibly occupy next turn, from our
        own belief's current best guess -- its likely current cell plus
        every legal one-step reply from there. 1-ply, not a full search:
        matches the round-trip depth this protocol's own turn order
        actually allows a live decision to look ahead."""
        cop_estimate = belief.most_likely()
        replies = [cop_estimate]
        for _direction, cell in board.legal_moves(cop_estimate, frozenset()):
            replies.append(cell)
        return replies

    def _softmax_pick(self, scored: list[tuple[float, Direction | None, Cell]]):
        """Among candidates within `_TIE_MARGIN` of the best score, sample
        by softmax instead of always taking the same one. A single
        candidate (or a single clear winner) returns deterministically;
        only genuine near-ties introduce variety."""
        if not scored:
            return None
        best_score = max(score for score, _, _ in scored)
        tied = [item for item in scored if item[0] >= best_score - _TIE_MARGIN]
        if len(tied) == 1:
            return tied[0]
        weights = [math.exp(score / _SOFTMAX_TEMPERATURE) for score, _, _ in tied]
        total = sum(weights)
        pick = self._rng.random() * total
        cumulative = 0.0
        for weight, item in zip(weights, tied, strict=True):
            cumulative += weight
            if pick <= cumulative:
                return item
        return tied[-1]

    def _pick_move(
        self,
        moves: list[tuple[Direction | None, Cell]],
        state: OwnGameState,
        belief,
        board: Board,
    ) -> tuple[Direction | None, Cell]:
        barriers = frozenset(state.known_barriers)
        cop_replies = self._cop_pessimistic_replies(belief, board)

        def score(cell: Cell) -> float:
            worst_case_distance = min(board.distance(cell, cop_next) for cop_next in cop_replies)
            danger = self._danger_penalty if worst_case_distance <= _DANGER_RADIUS else 0.0
            mobility = len(board.legal_moves(cell, barriers))
            recency = self._last_visited_turn.get(cell, -1)
            return (
                self._distance_weight * worst_case_distance
                + self._mobility_weight * mobility
                - danger
                - _RECENCY_WEIGHT * recency
            )

        scored = [(score(cell), direction, cell) for direction, cell in moves]
        picked = self._softmax_pick(scored)
        self._turn += 1
        if picked is None:
            return None, state.position
        _score, direction, cell = picked
        self._last_visited_turn[cell] = self._turn
        return direction, cell
