"""domain/scoring.py tests: Table 2 (book §3.5 "Win Conditions and
Scoring", p.22) scores by role, not winner/loser -- a captured thief
still scores `capture_thief` points, not zero. Pinned here so the
role-aware behavior can't silently regress back to a flat win/loss
scheme (docs/TodoCloseGaps.md #1)."""

from thief_peer.domain.scoring import aggregate_series, score_sub_game

_SCORING = {"capture_cop": 20, "capture_thief": 5, "survival_cop": 5, "survival_thief": 10}
_ROLES = {"Thief-Team": "thief", "Cop-Team": "cop"}


def test_score_sub_game_on_capture_scores_both_roles_from_the_table():
    assert score_sub_game("capture", _ROLES, _SCORING) == {"Cop-Team": 20, "Thief-Team": 5}


def test_score_sub_game_on_survival_scores_both_roles_from_the_table():
    assert score_sub_game("survival", _ROLES, _SCORING) == {"Cop-Team": 5, "Thief-Team": 10}


def test_score_sub_game_is_zero_zero_on_technical_loss():
    assert score_sub_game("timeout", _ROLES, _SCORING) == {"Cop-Team": 0, "Thief-Team": 0}


def test_score_sub_game_is_zero_zero_on_tamper_forfeit():
    assert score_sub_game("tamper_forfeit", _ROLES, _SCORING) == {"Cop-Team": 0, "Thief-Team": 0}


def test_score_sub_game_reads_the_correct_group_regardless_of_role_assignment():
    # Roles can be assigned to either group name -- the score must follow
    # the role, not which side happened to be "group_a" in some caller.
    swapped_roles = {"Cop-Team": "thief", "Thief-Team": "cop"}
    assert score_sub_game("capture", swapped_roles, _SCORING) == {
        "Thief-Team": 20,
        "Cop-Team": 5,
    }


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
