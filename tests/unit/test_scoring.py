"""domain/scoring.py tests: no numeric point formula is specified anywhere
in the rulebook excerpts available to us -- the chosen scheme (winner=1,
loser=0, tie=0/0) is a documented judgment call (README.md), pinned here
so it can't silently drift."""

from thief_peer.domain.scoring import aggregate_series, score_sub_game


def test_score_sub_game_gives_the_winner_one_point():
    assert score_sub_game("thief", "thief", "cop") == {"thief": 1, "cop": 0}


def test_score_sub_game_gives_the_other_winner_one_point():
    assert score_sub_game("cop", "thief", "cop") == {"thief": 0, "cop": 1}


def test_score_sub_game_is_zero_zero_on_a_tie():
    assert score_sub_game(None, "thief", "cop") == {"thief": 0, "cop": 0}


def test_aggregate_series_sums_scores_across_sub_games():
    sub_games = [
        {"score": {"thief": 1, "cop": 0}, "tie": False, "winner_group": "thief"},
        {"score": {"thief": 1, "cop": 0}, "tie": False, "winner_group": "thief"},
    ]
    result = aggregate_series(sub_games, "thief", "cop")

    assert result["total_score"] == {"thief": 2, "cop": 0}
    assert result["sub_games_won"] == {"thief": 2, "cop": 0}
    assert result["ties"] == 0
    assert result["winner_group"] == "thief"
    assert result["series_tie"] is False


def test_aggregate_series_is_a_series_tie_when_totals_are_equal():
    sub_games = [
        {"score": {"thief": 1, "cop": 0}, "tie": False, "winner_group": "thief"},
        {"score": {"thief": 0, "cop": 1}, "tie": False, "winner_group": "cop"},
    ]
    result = aggregate_series(sub_games, "thief", "cop")

    assert result["winner_group"] is None
    assert result["series_tie"] is True


def test_aggregate_series_counts_ties():
    sub_games = [{"score": {"thief": 0, "cop": 0}, "tie": True, "winner_group": None}]
    result = aggregate_series(sub_games, "thief", "cop")

    assert result["ties"] == 1
    assert result["sub_games_won"] == {"thief": 0, "cop": 0}


def test_aggregate_series_tokens_total_series_is_a_per_team_null_placeholder():
    # No LLM token-usage metering exists anywhere in this codebase --
    # honest `null` per team rather than a fabricated number.
    result = aggregate_series([], "thief", "cop")
    assert result["tokens_total_series"] == {"thief": None, "cop": None}
