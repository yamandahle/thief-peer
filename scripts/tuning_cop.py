"""Book-baseline Cop opponent + match simulator for tune_weights.py's
empirical sweep. Dev tooling only -- never imported by src/, never wired
into a real match; runs entirely offline against synthetic opponents, not
a real Cop implementation (respects rule 1/2's "one role per process" in
spirit by staying purely a local simulation).
"""

from thief_peer.domain.belief import BeliefGrid
from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.rules import is_captured_by_stuck
from thief_peer.domain.scent import ScentField
from thief_peer.strategy.fleeing_brain import ThiefBrain


class _SinglePeakBelief:
    """Perfect-information belief stand-in, matching
    tests/unit/test_fleeing_brain.py's own _single_peak_belief exactly --
    used only by average_distance_vs_naive_pursuer below, never by
    simulate_match (which uses the real BeliefGrid throughout)."""

    def __init__(self, size: int, target: Cell):
        self._matrix = [[0.0] * size for _ in range(size)]
        self._matrix[target[0]][target[1]] = 1.0

    def as_matrix(self):
        return self._matrix

    def most_likely(self):
        for r, row in enumerate(self._matrix):
            for c, p in enumerate(row):
                if p:
                    return (r, c)
        return (0, 0)


def book_baseline_cop_move(moves, belief, board: Board):
    """Book page 45/47's own default policy: minimize Manhattan distance
    to the believed Thief position -- mirrors test_fleeing_brain.py's
    _naive_pick_move (which maximizes, for the fleeing Thief)."""
    target = belief.most_likely()
    return min(moves, key=lambda m: board.distance(m[1], target))


def simulate_match(
    thief_weights: dict,
    cop_uses_belief: bool,
    board: Board,
    thief_start: Cell,
    cop_start: Cell,
    max_moves: int,
) -> int | None:
    """Runs one simulated match with real domain objects on both sides.
    Returns the step the Thief was captured on, or None if it survived to
    max_moves. `cop_uses_belief=True` selects the book-baseline opponent
    (real scent + belief, never sees the Thief's true position);
    `False` selects the existing weak floor opponent (cheats by pursuing
    the Thief's real position directly, no belief modeling at all --
    the same scripted-chase Cop already used in
    tests/unit/test_fleeing_brain.py)."""
    thief_state = OwnGameState(position=thief_start)
    cop_state = OwnGameState(position=cop_start)
    thief_brain = ThiefBrain(**thief_weights)
    thief_belief = BeliefGrid(board.size)
    cop_belief = BeliefGrid(board.size)
    thief_scent = ScentField(board.size)
    cop_scent = ScentField(board.size)

    for step in range(1, max_moves + 1):
        thief_belief.diffuse()
        thief_belief.observe_scent(cop_scent.snapshot())
        decision = thief_brain.decide(thief_state, board, thief_belief)
        thief_state.apply_move(decision.direction, board)
        thief_scent.advance(thief_state.position)

        cop_moves = board.legal_moves(cop_state.position, frozenset())
        if cop_uses_belief:
            cop_belief.diffuse()
            cop_belief.observe_scent(thief_scent.snapshot())
            cop_direction, _ = book_baseline_cop_move(cop_moves, cop_belief, board)
        else:
            cop_direction, _ = min(
                cop_moves, key=lambda m: board.distance(m[1], thief_state.position)
            )
        cop_state.apply_move(cop_direction, board)
        cop_scent.advance(cop_state.position)

        if cop_state.position == thief_state.position:
            return step
        if is_captured_by_stuck(thief_state, board):
            return step

    return None


def average_distance_vs_naive_pursuer(
    thief_weights: dict, board: Board, thief_start: Cell, cop_start: Cell, max_moves: int
) -> float:
    """Sanity check only, never used to pick weights: mirrors
    tests/unit/test_fleeing_brain.py's scripted-chase average-distance
    metric exactly (both sides get perfect position information, no
    scent/belief uncertainty). Book rule 27 forbids a real Cop from ever
    tracking exact position, so this isn't a legally-possible real
    opponent -- it's a pure algorithm-quality floor check, same role it
    already plays in that existing test."""
    thief_state = OwnGameState(position=thief_start)
    thief_brain = ThiefBrain(**thief_weights)
    cop_position = cop_start
    total_distance = 0
    for _ in range(max_moves):
        belief = _SinglePeakBelief(board.size, cop_position)
        decision = thief_brain.decide(thief_state, board, belief)
        thief_state.apply_move(decision.direction, board)
        cop_moves = board.legal_moves(cop_position, frozenset())
        _, cop_position = min(
            cop_moves, key=lambda m: board.distance(m[1], thief_state.position)
        )
        total_distance += board.distance(thief_state.position, cop_position)
    return total_distance / max_moves
