"""parse_direction_cue / hint_agrees_with_scent tests (book Ch.6.4, page 47;
Ch.4.4/6.4 lie-detection side)."""

from thief_peer.domain.hint_direction import hint_agrees_with_scent, parse_direction_cue


def test_no_direction_word_returns_none():
    assert parse_direction_cue("I'm nowhere near where you think I am.", 7) is None


def test_north_matches_the_top_half_of_rows():
    cue = parse_direction_cue("Last seen heading toward the north.", 8)
    assert cue == {f"{r},{c}": 1.0 for r in range(4) for c in range(8)}


def test_south_matches_the_bottom_half_of_rows():
    cue = parse_direction_cue("Somewhere down south.", 8)
    assert cue == {f"{r},{c}": 1.0 for r in range(4, 8) for c in range(8)}


def test_east_matches_the_right_half_of_columns():
    cue = parse_direction_cue("Slipping east along the river.", 8)
    assert cue == {f"{r},{c}": 1.0 for r in range(8) for c in range(4, 8)}


def test_west_matches_the_left_half_of_columns():
    cue = parse_direction_cue("Circling back to the west side.", 8)
    assert cue == {f"{r},{c}": 1.0 for r in range(8) for c in range(4)}


def test_case_insensitive_matching():
    cue = parse_direction_cue("NORTH of here.", 6)
    assert cue == {f"{r},{c}": 1.0 for r in range(3) for c in range(6)}


def test_diagonal_word_intersects_both_halves():
    cue = parse_direction_cue("Somewhere in the northeast.", 8)
    assert cue == {f"{r},{c}": 1.0 for r in range(4) for c in range(4, 8)}


def test_hyphenated_and_spaced_diagonal_forms_also_intersect():
    hyphenated = parse_direction_cue("north-east side of town.", 8)
    spaced = parse_direction_cue("north east side of town.", 8)
    expected = {f"{r},{c}": 1.0 for r in range(4) for c in range(4, 8)}
    assert hyphenated == expected
    assert spaced == expected


def test_reference_repo_sample_phrase_matches_northwest():
    # The book's own attached reference implementation's sample log
    # (docs/sample-run/log_*.json) literally contains this hint text.
    cue = parse_direction_cue("Near the north west side of New York.", 10)
    assert cue == {f"{r},{c}": 1.0 for r in range(5) for c in range(5)}


def test_conflicting_cardinal_words_place_no_constraint_on_that_axis():
    # "north" and "south" both present -- ambiguous, so rows stay
    # unconstrained (full range) rather than guessing.
    cue = parse_direction_cue("north or maybe south, hard to say.", 4)
    assert cue == {f"{r},{c}": 1.0 for r in range(4) for c in range(4)}


# ---- hint_agrees_with_scent (book ch.4.4/6.4) -----------------------------


def test_hint_agrees_with_scent_true_when_the_scent_peak_is_inside_the_region():
    region = parse_direction_cue("heading north", 8)
    scent = {"0,0": 0.9, "6,6": 0.1}  # peak (0,0) is in the north half

    assert hint_agrees_with_scent(region, scent) is True


def test_hint_agrees_with_scent_false_when_the_scent_peak_is_outside_the_region():
    region = parse_direction_cue("heading north", 8)
    scent = {"6,6": 0.9, "0,0": 0.1}  # peak (6,6) is in the south half -- a lie

    assert hint_agrees_with_scent(region, scent) is False


def test_hint_agrees_with_scent_is_none_when_the_hint_has_no_direction_word():
    region = parse_direction_cue("I'm nowhere near where you think I am.", 8)
    scent = {"0,0": 0.9}

    assert region is None
    assert hint_agrees_with_scent(region, scent) is None


def test_hint_agrees_with_scent_is_none_when_no_scent_was_reported_yet():
    region = parse_direction_cue("heading north", 8)

    assert hint_agrees_with_scent(region, {}) is None
