"""report/artifact_helpers.py tests (PRD_7 §3, §5). canonical_sha256 reuses
domain/crypto.py's canonical_json (Stage 6, DRY) -- never a second
hashing/serialization implementation."""

import hashlib

from thief_peer.domain.crypto import canonical_json
from thief_peer.report.artifact_helpers import (
    aggregate_series,
    artifact_filenames,
    canonical_sha256,
    merge_sub_games,
)


def test_canonical_sha256_matches_a_hand_computed_digest():
    payload = {"b": 2, "a": 1}
    expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    assert canonical_sha256(payload) == expected


def test_canonical_sha256_is_independent_of_dict_insertion_order():
    a = canonical_sha256({"grid_size": 7, "hint_word_limit": 15})
    b = canonical_sha256({"hint_word_limit": 15, "grid_size": 7})
    assert a == b


def test_artifact_filenames_match_the_book_appendix_naming_convention():
    names = artifact_filenames("group-a-vs-group-b", sub_game_number=3)

    assert names["declaration"] == "declaration_group-a-vs-group-b.json"
    assert names["config"] == "config_group-a-vs-group-b_g03.json"
    assert names["log"] == "log_group-a-vs-group-b_g03.json"
    assert names["result"] == "result_group-a-vs-group-b.json"


def test_artifact_filenames_declaration_and_result_are_per_match_not_per_sub_game():
    # Same game_id, different sub_game_number -> declaration/result filenames
    # must stay identical (once per match), only config/log vary.
    names1 = artifact_filenames("game-x", sub_game_number=1)
    names2 = artifact_filenames("game-x", sub_game_number=2)

    assert names1["declaration"] == names2["declaration"]
    assert names1["result"] == names2["result"]
    assert names1["config"] != names2["config"]
    assert names1["log"] != names2["log"]


def test_merge_sub_games_appends_a_new_sub_game_number():
    previous = [{"sub_game_number": 1, "score": {}}]
    merged = merge_sub_games(previous, {"sub_game_number": 2, "score": {}})

    assert [sg["sub_game_number"] for sg in merged] == [1, 2]


def test_merge_sub_games_replaces_not_duplicates_a_retried_sub_game():
    previous = [{"sub_game_number": 1, "score": {}, "result": "old"}]
    merged = merge_sub_games(previous, {"sub_game_number": 1, "score": {}, "result": "new"})

    assert len(merged) == 1
    assert merged[0]["result"] == "new"


def test_merge_sub_games_keeps_results_sorted_regardless_of_arrival_order():
    previous = [{"sub_game_number": 3, "score": {}}, {"sub_game_number": 1, "score": {}}]
    merged = merge_sub_games(previous, {"sub_game_number": 2, "score": {}})

    assert [sg["sub_game_number"] for sg in merged] == [1, 2, 3]


def test_aggregate_series_sums_score_across_every_recorded_sub_game():
    sub_games = [
        {"score": {"A": 10, "B": 5}, "winner_group": "A"},
        {"score": {"A": 5, "B": 20}, "winner_group": "B"},
    ]

    result = aggregate_series(sub_games, "A", "B")

    assert result["total_score"] == {"A": 15, "B": 25}
    assert result["sub_games_won"] == {"A": 1, "B": 1}


def test_aggregate_series_a_technical_loss_zero_score_still_counts_as_a_real_win():
    # A 0-0 technical-loss sub-game still has a book-mandated fault-based
    # winner (rule 19/35) -- aggregate_series must count that as a real
    # win, not silently drop it as a tie just because the score was 0-0.
    sub_games = [{"score": {"A": 0, "B": 0}, "winner_group": "B"}]

    result = aggregate_series(sub_games, "A", "B")

    assert result["sub_games_won"] == {"A": 0, "B": 1}
    assert result["winner_group"] == "B"
    assert result["series_tie"] is False


def test_aggregate_series_reports_a_genuine_series_tie():
    # Book p.71's own Tie Rule: tied on cumulative POINTS (25-25), not
    # just win-count -- swapped scores so both total_score and
    # sub_games_won land exactly even.
    sub_games = [
        {"score": {"A": 20, "B": 5}, "winner_group": "A"},
        {"score": {"A": 5, "B": 20}, "winner_group": "B"},
    ]

    result = aggregate_series(sub_games, "A", "B")

    assert result["total_score"] == {"A": 25, "B": 25}
    assert result["sub_games_won"] == {"A": 1, "B": 1}
    assert result["winner_group"] is None
    assert result["series_tie"] is True


def test_aggregate_series_uses_points_not_win_count_when_they_disagree():
    # A won more sub-games (2 vs 1), but B has more total points overall
    # -- the book's Tie Rule is explicit that cumulative points decide,
    # not how many individual sub-games each side happened to win.
    sub_games = [
        {"score": {"A": 5, "B": 5}, "winner_group": "A"},
        {"score": {"A": 5, "B": 5}, "winner_group": "A"},
        {"score": {"A": 5, "B": 30}, "winner_group": "B"},
    ]

    result = aggregate_series(sub_games, "A", "B")

    assert result["sub_games_won"] == {"A": 2, "B": 1}
    assert result["total_score"] == {"A": 15, "B": 40}
    assert result["winner_group"] == "B"
    assert result["series_tie"] is False


def test_aggregate_series_empty_list_is_a_tie_with_zero_everything():
    result = aggregate_series([], "A", "B")

    assert result == {
        "total_score": {"A": 0, "B": 0},
        "sub_games_won": {"A": 0, "B": 0},
        "ties": 0,
        "winner_group": None,
        "series_tie": True,
    }
