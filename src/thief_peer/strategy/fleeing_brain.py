"""ThiefBrain (PRD_3 Ch.6): a custom algorithm beyond the naive "maximize
distance from the belief peak" baseline the book ships by default (Ch.6.4).
Combines four signals -- full-distribution expected distance, mobility
(1-ply lookahead on legal moves from the candidate cell), a 1-ply minimax
lookahead against the Cop's best response, and a least-recently-visited
tie-break -- to resist corner-trapping, bimodal belief distributions, and
predictable straight-line trails (PRD_3 §2.2-2.3). Never touches an LLM.
"""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.brain_base import BrainBase

# Weighted-sum combination (PRD_3 §3): expected distance dominates in open
# space, but a large mobility gap (the signature of a real dead end, not
# just "slightly fewer options") can still outweigh a small distance edge --
# this is what keeps the Thief out of corners the naive single-peak-fleeing
# baseline walks straight into.
EXPECTED_DISTANCE_WEIGHT = 1.0
MOBILITY_WEIGHT = 1.5
LOOKAHEAD_WEIGHT = 0.1
TIE_EPSILON = 1e-6


class ThiefBrain(BrainBase):
    def __init__(self):
        self._last_visited_turn: dict[Cell, int] = {}
        self._turn = 0

    def _pick_move(
        self,
        moves: list[tuple[Direction | None, Cell]],
        state: OwnGameState,
        belief,
        board: Board,
    ) -> tuple[Direction | None, Cell]:
        barriers = frozenset(state.known_barriers)

        def score(cell: Cell) -> float:
            return (
                EXPECTED_DISTANCE_WEIGHT * self._expected_distance(cell, belief, board)
                + MOBILITY_WEIGHT * self._mobility_score(cell, board, barriers)
                + LOOKAHEAD_WEIGHT * self._lookahead_score(cell, belief, board)
            )

        scored = [(d, cell, score(cell)) for d, cell in moves]
        best_score = max(s for _, _, s in scored)
        tied = [(d, cell) for d, cell, s in scored if s >= best_score - TIE_EPSILON]

        direction, cell = min(
            tied, key=lambda item: self._last_visited_turn.get(item[1], -1)
        )

        self._turn += 1
        self._last_visited_turn[cell] = self._turn
        return direction, cell

    def _mobility_score(self, cell: Cell, board: Board, barriers: frozenset[Cell]) -> int:
        return len(board.legal_moves(cell, barriers))

    def _expected_distance(self, cell: Cell, belief, board: Board) -> float:
        matrix = belief.as_matrix()
        total = 0.0
        for r, row in enumerate(matrix):
            for c, probability in enumerate(row):
                if probability:
                    total += probability * board.distance(cell, (r, c))
        return total

    def _lookahead_score(self, cell: Cell, belief, board: Board) -> float:
        cop_estimate = belief.most_likely()
        cop_responses = board.legal_moves(cop_estimate, frozenset())
        return min(board.distance(cell, cop_next) for _, cop_next in cop_responses)
