"""ScentField tests (PRD_4 §2.1, §3, §5). advance() must reproduce the
book's Figure 4 kernel exactly and the additive (not max-merge) recurrence
-- rule 23 is [FATAL] on a decay-formula deviation, and an earlier draft of
this PRD got this wrong (see PRD_4 §4)."""

from thief_peer.domain.scent import ScentField, snapshot_to_matrix


def test_advance_on_empty_field_produces_exact_figure_4_kernel():
    field = ScentField(board_size=9)
    field.advance((4, 4))
    snap = field.snapshot()

    assert snap["4,4"] == 0.90
    # orthogonal neighbours
    assert snap["3,4"] == 0.62
    assert snap["5,4"] == 0.62
    assert snap["4,3"] == 0.62
    assert snap["4,5"] == 0.62
    # diagonal neighbours
    assert snap["3,3"] == 0.42
    assert snap["3,5"] == 0.42
    assert snap["5,3"] == 0.42
    assert snap["5,5"] == 0.42
    # range-two orthogonal
    assert snap["2,4"] == 0.20
    assert snap["4,2"] == 0.20
    # range-two diagonal-ish
    assert snap["2,3"] == 0.14
    assert snap["3,2"] == 0.14
    # corners of the 5x5 kernel
    assert snap["2,2"] == 0.04
    assert snap["6,6"] == 0.04


def test_advance_clips_kernel_cells_that_fall_outside_the_board():
    field = ScentField(board_size=9)
    field.advance((0, 0))
    snap = field.snapshot()

    assert "-1,0" not in snap
    assert "0,-1" not in snap
    assert "-2,-2" not in snap
    # the corner itself and its in-bounds neighbours are still present
    assert snap["0,0"] == 0.90
    assert snap["1,0"] == 0.62


def test_advance_composes_additively_not_by_max_merge():
    field = ScentField(board_size=9)
    field.advance((4, 4))
    field.advance((4, 4))
    snap = field.snapshot()

    # additive recurrence: tau(2) = (1-rho)*tau(1) + kernel_center
    expected_center = (1 - 0.10) * 0.90 + 0.90
    assert snap["4,4"] == expected_center
    # explicitly NOT the old (buggy) max-merge behaviour
    max_merge_center = max((1 - 0.10) * 0.90, 0.90)
    assert snap["4,4"] != max_merge_center


def test_advance_accumulates_correctly_over_n_repeated_calls():
    field = ScentField(board_size=9)
    rho = 0.10
    kernel_center = 0.90
    expected = 0.0
    for _ in range(5):
        expected = expected * (1 - rho) + kernel_center
        field.advance((4, 4))

    assert field.snapshot()["4,4"] == expected


def test_advance_decays_a_cell_that_is_no_longer_hit_by_the_kernel():
    field = ScentField(board_size=9)
    field.advance((4, 4))
    first = field.snapshot()["4,4"]

    field.advance((0, 0))  # far away -- (4,4) only decays now
    second = field.snapshot()["4,4"]

    assert second == first * (1 - 0.10)


def test_snapshot_is_sparse_and_omits_zero_entries():
    field = ScentField(board_size=9)
    field.advance((4, 4))  # fully in-bounds 5x5 kernel, nothing clipped
    snap = field.snapshot()

    assert "0,0" not in snap
    assert len(snap) == 25


def test_absorb_overwrites_the_locally_held_field_with_received_data():
    field = ScentField(board_size=9)
    field.advance((4, 4))  # some pre-existing local state

    field.absorb({"1,1": 0.5, "1,2": 0.3})
    snap = field.snapshot()

    assert snap == {"1,1": 0.5, "1,2": 0.3}


def test_center_intensity_scales_the_whole_kernel_proportionally():
    field = ScentField(board_size=9, center_intensity=0.45)  # half of the book's 0.9
    field.advance((4, 4))
    snap = field.snapshot()

    assert snap["4,4"] == 0.45
    assert snap["3,4"] == 0.31  # 0.62 * 0.5


def test_snapshot_to_matrix_places_each_value_at_its_own_cell():
    matrix = snapshot_to_matrix({"0,0": 0.9, "1,2": 0.5}, size=3)

    assert matrix == [[0.9, 0.0, 0.0], [0.0, 0.0, 0.5], [0.0, 0.0, 0.0]]


def test_snapshot_to_matrix_empty_snapshot_is_all_zeros():
    matrix = snapshot_to_matrix({}, size=2)

    assert matrix == [[0.0, 0.0], [0.0, 0.0]]
