"""BeliefGrid tests (PRD_4 §2.3, §3, §5). observe_scent() is the only
update path -- a hint is never accepted as an input at all, which is the
structural proof that a verbal claim can never outweigh the unfakeable
scent signal (book Ch.4.4/6.4's lie-detection worked example)."""

from thief_peer.domain.belief import BeliefGrid


def test_init_is_uniform_over_all_cells():
    belief = BeliefGrid(board_size=3)
    matrix = belief.as_matrix()

    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)
    for row in matrix:
        for p in row:
            assert p == 1 / 9


def test_observe_scent_matches_hand_computed_reweighting():
    belief = BeliefGrid(board_size=3)
    belief.observe_scent({"1,1": 1.0})
    matrix = belief.as_matrix()

    assert abs(matrix[1][1] - 0.2) < 1e-9
    assert abs(matrix[0][0] - 0.1) < 1e-9
    assert abs(matrix[2][2] - 0.1) < 1e-9
    total = sum(sum(row) for row in matrix)
    assert abs(total - 1.0) < 1e-9


def test_observe_scent_never_accepts_a_hint_argument():
    # Structural guarantee: BeliefGrid.observe_scent only ever takes the
    # scent snapshot -- there is no parameter a hint string could occupy.
    import inspect

    params = inspect.signature(BeliefGrid.observe_scent).parameters
    assert "hint" not in params
    assert list(params)[1] == "cells"


def test_diffuse_conserves_total_probability_mass():
    belief = BeliefGrid(board_size=5)
    belief.observe_scent({"2,2": 3.0})  # sharpen the peak before diffusing
    before = sum(sum(row) for row in belief.as_matrix())

    belief.diffuse()
    after = sum(sum(row) for row in belief.as_matrix())

    assert abs(before - 1.0) < 1e-9
    assert abs(after - 1.0) < 1e-9


def test_diffuse_spreads_a_concentrated_center_peak_to_its_five_neighbours():
    belief = BeliefGrid(board_size=3)
    belief.observe_scent({"1,1": 1e9})  # collapse ~all mass onto (1,1)
    belief.diffuse()
    matrix = belief.as_matrix()

    # center (1,1) has 4 in-bounds orthogonal neighbours + STAY = 5 shares
    for r, c in [(1, 1), (0, 1), (2, 1), (1, 0), (1, 2)]:
        assert abs(matrix[r][c] - 0.2) < 1e-6
    assert matrix[0][0] < 1e-6


def test_diffuse_from_a_corner_splits_across_only_its_in_bounds_neighbours():
    belief = BeliefGrid(board_size=3)
    belief.observe_scent({"0,0": 1e9})  # collapse ~all mass onto the corner
    belief.diffuse()
    matrix = belief.as_matrix()

    # corner (0,0): only STAY, S(1,0), E(0,1) are in bounds -- 3 shares
    for r, c in [(0, 0), (1, 0), (0, 1)]:
        assert abs(matrix[r][c] - 1 / 3) < 1e-6


def test_most_likely_returns_the_argmax_cell():
    belief = BeliefGrid(board_size=5)
    belief.observe_scent({"3,4": 10.0})

    assert belief.most_likely() == (3, 4)


def test_observe_declaration_concentrates_trust_on_the_declared_cell():
    belief = BeliefGrid(board_size=5)
    belief.observe_declaration((2, 2), radius=0, trust=0.9)
    matrix = belief.as_matrix()

    assert abs(matrix[2][2] - 0.9) < 1e-9
    total = sum(sum(row) for row in matrix)
    assert abs(total - 1.0) < 1e-9


def test_observe_declaration_radius_one_spreads_trust_over_the_orthogonal_cross():
    belief = BeliefGrid(board_size=5)
    belief.observe_declaration((2, 2), radius=1, trust=0.9)
    matrix = belief.as_matrix()

    cross = [(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)]
    declared_mass = sum(matrix[r][c] for r, c in cross)
    assert abs(declared_mass - 0.9) < 1e-9
    # A diagonal neighbor is NOT part of the radius-1 orthogonal cross.
    assert matrix[1][1] < matrix[2][2]


def test_observe_declaration_never_zeroes_out_the_rest_of_the_board():
    # Rule 21/22: lying about a capture is a real, permitted-to-happen
    # violation, not something structurally impossible -- so a declaration
    # must never collapse belief to certainty the way observe_scent's own
    # unfakeable signal is allowed to.
    belief = BeliefGrid(board_size=5)
    belief.observe_declaration((0, 0), radius=0, trust=0.99)
    matrix = belief.as_matrix()

    for r in range(5):
        for c in range(5):
            if (r, c) != (0, 0):
                assert matrix[r][c] > 0.0


def test_observe_declaration_composes_with_observe_scent_and_stays_normalized():
    belief = BeliefGrid(board_size=5)
    belief.observe_scent({"1,1": 0.5})
    belief.observe_declaration((3, 3), radius=0, trust=0.8)
    total = sum(sum(row) for row in belief.as_matrix())
    assert abs(total - 1.0) < 1e-9


def test_lie_detection_scent_alone_drives_belief_regardless_of_any_claim():
    # Mirrors the book's Ch.4.4 worked example: a scent field concentrated
    # in one region wins out over any opposing claim, because BeliefGrid
    # structurally never receives the claim/hint text at all.
    belief = BeliefGrid(board_size=7)
    belief.observe_scent({"5,6": 0.9, "5,5": 0.62, "6,6": 0.62})  # southeast

    likely = belief.most_likely()
    assert likely in {(5, 6), (5, 5), (6, 6)}
    # Whatever a hint might have claimed ("I moved north"), the far side of
    # the board is nowhere near the winning cell.
    assert likely[0] >= 5 and likely[1] >= 5
