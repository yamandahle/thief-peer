"""ThiefBrain tests (PRD_3 §2.2-2.3, §5). Each helper is hand-verified on
a small fixed board, mirroring the book's own worked-example style, then
the combined `_pick_move` is checked against the corner-trap and
bimodal-belief scenarios the naive single-peak baseline gets wrong."""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.fleeing_brain import ThiefBrain


class _FixedBelief:
    """Test-only belief exposing the same as_matrix()/most_likely()
    interface Stage 4's real BeliefGrid will (PRD_3 scope note) -- built
    from an explicit matrix so bimodal distributions are easy to construct."""

    def __init__(self, matrix):
        self._matrix = matrix

    def as_matrix(self):
        return self._matrix

    def most_likely(self):
        best_cell, best_p = (0, 0), -1.0
        for r, row in enumerate(self._matrix):
            for c, p in enumerate(row):
                if p > best_p:
                    best_cell, best_p = (r, c), p
        return best_cell


def _single_peak_belief(size, target):
    matrix = [[0.0] * size for _ in range(size)]
    matrix[target[0]][target[1]] = 1.0
    return _FixedBelief(matrix)


def _naive_pick_move(moves, belief, board):
    """The book's own shipped baseline (PRD_3 §2.1): flee the single belief
    peak, ignore mobility/lookahead entirely. Used as the comparison floor
    our custom algorithm must beat."""
    target = belief.most_likely()
    return max(moves, key=lambda m: board.distance(m[1], target))


# ---- helpers, hand-computed -------------------------------------------


def test_mobility_score_counts_legal_moves_from_a_cell():
    board = Board(size=7, barriers=set())
    brain = ThiefBrain()
    # center cell: N, S, E, W, STAY = 5
    assert brain._mobility_score((3, 3), board, frozenset()) == 5
    # corner cell: only S, E, STAY = 3
    assert brain._mobility_score((0, 0), board, frozenset()) == 3


def test_expected_distance_matches_hand_computed_value():
    board = Board(size=3, barriers=set())
    brain = ThiefBrain()
    # Two peaks of equal mass 0.5 at (0,0) and (2,2). Candidate cell (0,2):
    # distance to (0,0) = 2, distance to (2,2) = 2 -> expected = 0.5*2+0.5*2=2
    matrix = [[0.0] * 3 for _ in range(3)]
    matrix[0][0] = 0.5
    matrix[2][2] = 0.5
    belief = _FixedBelief(matrix)
    assert brain._expected_distance((0, 2), belief, board) == 2.0


def test_lookahead_score_is_cops_best_response_distance():
    # Cop believed at (3,3) (single peak). Thief candidate move to (3,0).
    # Cop's best 1-ply response minimizes distance to (3,0): moving to
    # (3,2) yields distance 2, which is the closest the Cop can get.
    board = Board(size=7, barriers=set())
    brain = ThiefBrain()
    belief = _single_peak_belief(7, (3, 3))
    score = brain._lookahead_score((3, 0), belief, board)
    assert score == 2


def test_lookahead_score_weights_multiple_candidate_cop_positions_by_belief():
    # book Ch.6.3.1 (page 45): expectimax against the belief distribution,
    # not a single collapsed most_likely() point. Two candidates, p=0.6 at
    # (0,6) and p=0.4 at (6,0), on a 7x7 empty board; Thief candidate (0,3).
    # Cop at (0,6): legal moves S(1,6)/W(0,5)/STAY(0,6) -- best response
    # distance to (0,3) is via W -> (0,5), distance 2.
    # Cop at (6,0): legal moves N(5,0)/E(6,1)/STAY(6,0) -- best response
    # distance to (0,3) is via N -> (5,0), distance 8.
    # Expected weighted score: 0.6*2 + 0.4*8 = 4.4 -- strictly different
    # from either candidate's own answer alone (2 or 8).
    board = Board(size=7, barriers=set())
    brain = ThiefBrain()
    matrix = [[0.0] * 7 for _ in range(7)]
    matrix[0][6] = 0.6
    matrix[6][0] = 0.4
    belief = _FixedBelief(matrix)

    score = brain._lookahead_score((0, 3), belief, board)

    assert abs(score - 4.4) < 1e-9


def test_lookahead_score_returns_zero_when_belief_is_entirely_empty():
    # Defensive: BeliefGrid always normalizes to sum 1 in practice, but an
    # all-zero matrix must degrade safely (no division by zero) rather than
    # crash.
    board = Board(size=5, barriers=set())
    brain = ThiefBrain()
    belief = _FixedBelief([[0.0] * 5 for _ in range(5)])

    assert brain._lookahead_score((2, 2), belief, board) == 0.0


# ---- combined behaviour --------------------------------------------------


def test_pick_move_never_returns_a_move_outside_the_legal_list():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    brain = ThiefBrain()
    belief = _single_peak_belief(5, (0, 0))
    moves = board.legal_moves(state.position, frozenset())
    chosen = brain._pick_move(moves, state, belief, board)
    assert chosen in moves


def test_beats_naive_single_peak_baseline_over_a_scripted_chase():
    # A pursuing Cop scripted to always step toward the Thief's *previous*
    # cell (simple, fixed pursuit -- no belief modeling on the Cop's side,
    # this is just a fixed opponent to measure survival distance against).
    # The board's SE corner is walled into a one-wide dead-end pocket
    # ((5,6)/(4,6) barred) -- exactly the trap the naive single-peak-fleeing
    # baseline walks straight into (it's the single farthest cell from the
    # Cop's starting corner), while mobility-aware scoring should route
    # around it.
    barriers = {(5, 6), (4, 6)}
    board = Board(size=7, barriers=barriers)

    def run(brain_pick_fn):
        state = OwnGameState(position=(3, 3))
        cop = (0, 0)
        total_distance = 0
        for _ in range(30):
            belief = _single_peak_belief(7, cop)
            moves = board.legal_moves(state.position, board.barriers)
            direction, dest = brain_pick_fn(moves, state, belief, board)
            state.apply_move(direction, board)
            # Cop greedily steps toward the Thief's new position.
            cop_moves = board.legal_moves(cop, frozenset())
            _, cop = min(cop_moves, key=lambda m: board.distance(m[1], state.position))
            total_distance += board.distance(state.position, cop)
        return total_distance / 30

    thief_brain = ThiefBrain()
    smart_avg = run(lambda moves, state, belief, board: thief_brain._pick_move(moves, state, belief, board))
    naive_avg = run(lambda moves, state, belief, board: _naive_pick_move(moves, belief, board))

    assert smart_avg > naive_avg


def test_corner_avoidance_prefers_higher_mobility_over_raw_distance():
    # Thief at (1,0) on a 5x5 board. Belief peak far at (4,4). The move
    # maximizing raw distance from (4,4) is W... but (1,0) is already at
    # the west wall, so the naive baseline's top pick walks toward the
    # (0,0) corner (N), which has only 2 legal exits next turn, while a
    # move that keeps similar distance but higher mobility (S, toward open
    # board) should be preferred by the mobility-aware scoring.
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(1, 0))
    brain = ThiefBrain()
    belief = _single_peak_belief(5, (4, 4))
    moves = board.legal_moves(state.position, frozenset())

    naive_direction, naive_dest = _naive_pick_move(moves, belief, board)
    smart_direction, smart_dest = brain._pick_move(moves, state, belief, board)

    naive_mobility = brain._mobility_score(naive_dest, board, frozenset())
    smart_mobility = brain._mobility_score(smart_dest, board, frozenset())

    assert naive_direction == Direction.N
    assert naive_mobility < smart_mobility


def test_bimodal_belief_produces_better_expected_distance_than_naive_peak_targeting():
    # Two peaks of equal mass -- naive argmax-targeting picks whichever peak
    # ties first and flees only that one; the expected-distance scoring
    # should produce a move with strictly better total expected distance
    # across both peaks.
    board = Board(size=9, barriers=set())
    state = OwnGameState(position=(4, 4))
    brain = ThiefBrain()

    matrix = [[0.0] * 9 for _ in range(9)]
    matrix[0][0] = 0.5
    matrix[0][8] = 0.5
    belief = _FixedBelief(matrix)
    moves = board.legal_moves(state.position, frozenset())

    naive_direction, naive_dest = _naive_pick_move(moves, belief, board)
    smart_direction, smart_dest = brain._pick_move(moves, state, belief, board)

    naive_expected = brain._expected_distance(naive_dest, belief, board)
    smart_expected = brain._expected_distance(smart_dest, belief, board)

    assert smart_expected >= naive_expected
