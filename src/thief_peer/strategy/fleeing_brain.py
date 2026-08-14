"""ThiefBrain (PRD_3 Ch.6): a custom algorithm beyond the naive "maximize
distance from the belief peak" baseline the book ships by default (Ch.6.4).
Combines five signals -- full-distribution expected distance, mobility
(1-ply lookahead on legal moves from the candidate cell), a 1-ply
expectimax lookahead against the top candidate Cop positions weighted by
belief probability (book Ch.6.3.1, page 45: "forward search... expectimax
against the opponent's belief" -- reasons over the distribution itself,
not a single most_likely() point), a scent-concentration cost (book
ch.1.4, p.6: staying in or returning to a cell only makes that cell's own
trail *stronger*, which helps the opponent find it -- a real cost, unlike
the verbal hint, which can lie), and a least-recently-visited tie-break --
to resist corner-trapping, bimodal belief distributions, and predictable
straight-line trails (PRD_3 §2.2-2.3). Never touches an LLM.
"""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.brain_base import BrainBase
from thief_peer.strategy.trash_talk import choose_verdict

# Weighted-sum combination (PRD_3 §3): expected distance dominates in open
# space, but a large mobility gap (the signature of a real dead end, not
# just "slightly fewer options") can still outweigh a small distance edge --
# this is what keeps the Thief out of corners the naive single-peak-fleeing
# baseline walks straight into.
#
# REVERTED (2026-08-12) from an empirically-"tuned" 2.0/1.5/0.5/10: that
# configuration scored well (77% win rate) against scripts/tune_weights.py's
# simulated opponent, but that simulator only ever moves -- it never places
# a barrier, so it can never punish camping in a corner. In real matches
# against the actual Cop repo (6 real games, --warmup), the higher
# EXPECTED_DISTANCE_WEIGHT made corners look locally optimal (often the
# single farthest cell from the believed Cop position) and the Thief
# repeatedly chose STAY there for many consecutive rounds instead of
# escaping, letting the real Cop wall it in with barriers -- 5 of 6 losses,
# all via the identical STAY-camping-in-the-corner pattern (see
# peer/round_reporter.py's live output, which is what caught this). Real
# win rate across all real matches so far: 2/7 (~29%), worse than these
# original values. A simulator that actually models barrier placement is
# needed before attempting to re-tune -- see the open item in
# scripts/tuning_cop.py's module docstring.
EXPECTED_DISTANCE_WEIGHT = 1.0
MOBILITY_WEIGHT = 1.5
LOOKAHEAD_WEIGHT = 0.1
# Not yet empirically tuned (see scripts/tune_weights.py's own open item,
# item 18 in docs/BOOK_WALKTHROUGH.md) -- picked in between LOOKAHEAD_WEIGHT
# and EXPECTED_DISTANCE_WEIGHT deliberately, so a heavily-revisited cell
# gets a real, felt penalty without ever being able to outweigh a genuine
# mobility-based escape route (MOBILITY_WEIGHT) the way an over-tuned
# EXPECTED_DISTANCE_WEIGHT once did -- see this file's own corner-camping
# history above.
SCENT_WEIGHT = 0.5
TIE_EPSILON = 1e-6

# Top-N highest-probability belief cells considered as candidate Cop
# positions in the expectimax lookahead -- keeps the search tractable
# without discarding the distribution the way a single most_likely()
# point does.
LOOKAHEAD_CANDIDATE_COUNT = 5


class ThiefBrain(BrainBase):
    def __init__(
        self,
        expected_distance_weight: float = EXPECTED_DISTANCE_WEIGHT,
        mobility_weight: float = MOBILITY_WEIGHT,
        lookahead_weight: float = LOOKAHEAD_WEIGHT,
        lookahead_candidate_count: int = LOOKAHEAD_CANDIDATE_COUNT,
        scent_weight: float = SCENT_WEIGHT,
    ):
        # Overridable only for scripts/tune_weights.py's empirical sweep --
        # every real caller (resolve_brain's default) uses the module
        # constants above, unchanged.
        self._expected_distance_weight = expected_distance_weight
        self._mobility_weight = mobility_weight
        self._lookahead_weight = lookahead_weight
        self._lookahead_candidate_count = lookahead_candidate_count
        self._scent_weight = scent_weight
        self._last_visited_turn: dict[Cell, int] = {}
        self._turn = 0

    def _pick_move(
        self,
        moves: list[tuple[Direction | None, Cell]],
        state: OwnGameState,
        belief,
        board: Board,
        own_scent: dict[str, float],
    ) -> tuple[Direction | None, Cell]:
        barriers = frozenset(state.known_barriers)

        def score(cell: Cell) -> float:
            return (
                self._expected_distance_weight * self._expected_distance(cell, belief, board)
                + self._mobility_weight * self._mobility_score(cell, board, barriers)
                + self._lookahead_weight * self._lookahead_score(cell, belief, board)
                + self._scent_weight * self._scent_score(cell, own_scent)
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

    def _choose_verdict(self, cell: Cell, belief, board: Board) -> str:
        """Book ch.6.5/1.4: reuses the same expected-distance signal already
        computed for movement (`_expected_distance`) rather than a second,
        separately-tuned figure -- lying is worth more when the opponent's
        belief is already close to the truth, honesty costs little when
        it's already far off. `max_possible_distance` is the board's own
        corner-to-corner distance, the same normalization scale
        `choose_verdict` expects."""
        max_possible_distance = board.distance((0, 0), (board.size - 1, board.size - 1))
        expected_distance = self._expected_distance(cell, belief, board)
        return choose_verdict(expected_distance, max_possible_distance)

    def _mobility_score(self, cell: Cell, board: Board, barriers: frozenset[Cell]) -> int:
        return len(board.legal_moves(cell, barriers))

    def _scent_score(self, cell: Cell, own_scent: dict[str, float]) -> float:
        """Book ch.1.4, p.6: a scent trail can't be faked -- staying in or
        returning to a cell only reinforces this side's *own* trail there,
        which is a cost (easier for the opponent to find), never an
        advantage. `own_scent` is this side's own pre-move snapshot
        (`ScentField.snapshot()`, the same sparse `{"r,c": intensity}` shape
        sent to the opponent), so a candidate cell already carrying a
        strong residual trail scores negatively here -- the higher the
        existing intensity, the stronger the discouragement."""
        r, c = cell
        return -own_scent.get(f"{r},{c}", 0.0)

    def _expected_distance(self, cell: Cell, belief, board: Board) -> float:
        matrix = belief.as_matrix()
        total = 0.0
        for r, row in enumerate(matrix):
            for c, probability in enumerate(row):
                if probability:
                    total += probability * board.distance(cell, (r, c))
        return total

    def _lookahead_score(self, cell: Cell, belief, board: Board) -> float:
        """Expectimax against the opponent's belief distribution (book
        Ch.6.3.1, page 45): the Cop's best 1-ply response distance,
        weighted by belief probability across the top candidate positions
        -- not just a single collapsed guess."""
        matrix = belief.as_matrix()
        candidates = sorted(
            (
                (p, (r, c))
                for r, row in enumerate(matrix)
                for c, p in enumerate(row)
                if p > 0
            ),
            reverse=True,
        )[: self._lookahead_candidate_count]
        if not candidates:
            return 0.0

        total_weight = sum(p for p, _ in candidates)
        weighted_sum = 0.0
        for p, cop_pos in candidates:
            cop_responses = board.legal_moves(cop_pos, frozenset())
            best_cop_response = min(
                board.distance(cell, cop_next) for _, cop_next in cop_responses
            )
            weighted_sum += p * best_cop_response
        return weighted_sum / total_weight
