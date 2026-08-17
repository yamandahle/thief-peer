"""ScentField tests (PRD_4 §2.1, §3, §5). advance() must reproduce the
book's Figure 4 kernel exactly and the additive (not max-merge) recurrence
-- rule 23 is [FATAL] on a decay-formula deviation, and an earlier draft of
this PRD got this wrong (see PRD_4 §4)."""

from thief_peer.domain.scent import ScentField


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
    # Use a low-intensity kernel cell (the 0.04 corner), not the 0.90 centre:
    # two centre deposits already sum past the 0.9 cap (see
    # test_advance_caps_at_center_intensity_when_deposits_saturate below),
    # which would make additive and max-merge composition indistinguishable
    # once both are clamped to the same cap value.
    field = ScentField(board_size=9)
    field.advance((4, 4))
    field.advance((4, 4))
    snap = field.snapshot()

    # additive recurrence: tau(2) = (1-rho)*tau(1) + kernel_corner
    expected_corner = (1 - 0.10) * 0.04 + 0.04
    assert snap["2,2"] == expected_corner
    # explicitly NOT the old (buggy) max-merge behaviour
    max_merge_corner = max((1 - 0.10) * 0.04, 0.04)
    assert snap["2,2"] != max_merge_corner


def test_advance_accumulates_correctly_over_n_repeated_calls():
    # Same reasoning as above: track the 0.04 corner so the accumulating sum
    # stays well under the 0.9 cap across all 5 iterations, keeping this a
    # test of the additive recurrence itself rather than of the cap.
    field = ScentField(board_size=9)
    rho = 0.10
    kernel_corner = 0.04
    expected = 0.0
    for _ in range(5):
        expected = expected * (1 - rho) + kernel_corner
        field.advance((4, 4))

    assert expected < 0.9  # sanity: this run never actually engages the cap
    assert field.snapshot()["2,2"] == expected


def test_advance_caps_at_center_intensity_when_deposits_saturate():
    # Appendix E / book Ch.4.3: tau(t+1) = min(0.9, max(0, (1-rho)*tau(t) +
    # delta_tau)). Repeated centre deposits sum past 0.9 immediately, so the
    # held value must pin at the cap, never grow past it.
    field = ScentField(board_size=9)
    for _ in range(5):
        field.advance((4, 4))

    assert field.snapshot()["4,4"] == 0.90


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
