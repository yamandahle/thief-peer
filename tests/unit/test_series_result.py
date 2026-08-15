"""report/series_result.py tests: `merge_sub_game_into_series` is the
stateful counterpart to artifacts.py's pure builders -- it owns reading
whatever `result_<game_id>.json` already exists, replacing/appending this
sub-game, and recomputing `final_result` from the complete array. Mirrors
the real Cop peer's own reference implementation (no separate state file;
`sub_games` state lives inside the result artifact itself)."""

from thief_peer.report.series_result import merge_sub_game_into_series


def _sub_game(number, winner="thief", score=None, log_verified=True):
    score = score or ({"thief": 1, "cop": 0} if winner == "thief" else {"thief": 0, "cop": 1})
    return {
        "sub_game_number": number,
        "winner_group": winner,
        "tie": False,
        "score": score,
        "audit": {"log_verified": log_verified, "peer_audit_passed": True, "tampered": False},
    }


def test_first_sub_game_creates_a_fresh_series_with_a_new_game_uid(tmp_path):
    result = merge_sub_game_into_series(tmp_path, "thief-vs-cop", "thief", "cop", 3, _sub_game(1), 1)

    assert result["sub_games"] == [_sub_game(1)]
    assert result["game_uid"]
    assert result["final_result"]["total_score"] == {"thief": 1, "cop": 0}


def test_a_second_sub_game_appends_and_reaggregates(tmp_path):
    first = merge_sub_game_into_series(tmp_path, "thief-vs-cop", "thief", "cop", 2, _sub_game(1), 1)
    (tmp_path / "result_thief-vs-cop.json").write_text(__import__("json").dumps(first))

    second = merge_sub_game_into_series(
        tmp_path, "thief-vs-cop", "thief", "cop", 2, _sub_game(2, winner="cop"), 2
    )

    assert [sg["sub_game_number"] for sg in second["sub_games"]] == [1, 2]
    assert second["final_result"]["total_score"] == {"thief": 1, "cop": 1}
    assert second["final_result"]["series_tie"] is True


def test_re_calling_with_the_same_sub_game_number_replaces_not_duplicates(tmp_path):
    import json

    first = merge_sub_game_into_series(tmp_path, "thief-vs-cop", "thief", "cop", 1, _sub_game(1), 1)
    (tmp_path / "result_thief-vs-cop.json").write_text(json.dumps(first))

    replayed = merge_sub_game_into_series(
        tmp_path, "thief-vs-cop", "thief", "cop", 1, _sub_game(1, winner="cop"), 1
    )

    assert len(replayed["sub_games"]) == 1
    assert replayed["sub_games"][0]["winner_group"] == "cop"


def test_game_uid_stays_stable_across_calls(tmp_path):
    import json

    first = merge_sub_game_into_series(tmp_path, "thief-vs-cop", "thief", "cop", 2, _sub_game(1), 1)
    (tmp_path / "result_thief-vs-cop.json").write_text(json.dumps(first))

    second = merge_sub_game_into_series(
        tmp_path, "thief-vs-cop", "thief", "cop", 2, _sub_game(2), 2
    )

    assert second["game_uid"] == first["game_uid"]


def test_mutual_agreement_sha256_changes_if_sub_game_content_changes(tmp_path):
    a = merge_sub_game_into_series(tmp_path, "thief-vs-cop", "thief", "cop", 1, _sub_game(1), 1)
    b = merge_sub_game_into_series(
        tmp_path, "thief-vs-cop", "thief", "cop", 1, _sub_game(1, winner="cop"), 1
    )

    assert a["mutual_agreement"]["sha256"] != b["mutual_agreement"]["sha256"]


def test_mutual_agreement_confirmed_is_false_if_any_sub_game_audit_failed(tmp_path):
    result = merge_sub_game_into_series(
        tmp_path, "thief-vs-cop", "thief", "cop", 1, _sub_game(1, log_verified=False), 1
    )

    assert result["mutual_agreement"]["confirmed"] is False


def test_a_stale_pre_schema_result_file_on_disk_does_not_crash(tmp_path):
    # A real result_<game_id>.json written before this schema existed has
    # no `game_uid`/`sub_games` at all -- must be treated as absent, not
    # crash on the first match run after upgrading.
    import json

    (tmp_path / "result_thief-vs-cop.json").write_text(
        json.dumps(
            {
                "schema_version": "1.2",
                "final_result": {"winner_group": "thief", "tokens_total_series": 0},
                "mutual_agreement_signature": None,
            }
        )
    )

    result = merge_sub_game_into_series(tmp_path, "thief-vs-cop", "thief", "cop", 1, _sub_game(1), 1)

    assert result["sub_games"] == [_sub_game(1)]
    assert result["game_uid"]


def test_bonus_fields_are_populated_honestly(tmp_path):
    result = merge_sub_game_into_series(tmp_path, "thief-vs-cop", "thief", "cop", 1, _sub_game(1), 5)

    assert result["final_result"]["games_played_including_this"] == 5
    assert result["final_result"]["diversity_reward_applied"] is False
