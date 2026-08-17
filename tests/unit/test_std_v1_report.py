"""interop/std_v1/report.py tests: builds the Section-12
result_<game_id>.json shape. final_result's +2 series-tie bonus is the
trickiest rule here -- applied once to each side, only when the raw
cumulative totals were equal before the bonus."""

from thief_peer.interop.std_v1.report import build_result_report, final_result, group_details, valid_commit


def test_valid_commit_accepts_exactly_40_hex_chars():
    assert valid_commit("a" * 40) == "a" * 40


def test_valid_commit_rejects_wrong_length_or_non_hex():
    assert valid_commit("a" * 39) == ""
    assert valid_commit("g" * 40) == ""
    assert valid_commit(None) == ""
    assert valid_commit(12345) == ""


def test_group_details_defaults_missing_fields_to_empty():
    assert group_details({}) == {
        "group_id": "", "members": [], "repos": {}, "mcp_servers": {}, "llm_model": "", "hardware_spec": {},
    }


def _row(winner, my_score, their_score):
    return {"sub_game_number": 1, "result": "capture", "roles": {}, "score": {"A": my_score, "B": their_score}, "winner_group": winner}


def test_final_result_no_bonus_when_totals_differ():
    rows = [_row("A", 20, 5), _row("A", 5, 0)]
    result = final_result(rows, "A", "B")
    assert result["total_score"] == {"A": 25, "B": 5}
    assert result["winner_group"] == "A"
    assert result["series_tie"] is False
    assert result["sub_games_won"] == {"A": 2, "B": 0}


def test_final_result_applies_plus_two_bonus_once_each_side_on_a_raw_tie():
    rows = [_row("A", 10, 5), _row("B", 5, 10)]  # raw totals: A=15, B=15
    result = final_result(rows, "A", "B")
    assert result["total_score"] == {"A": 17, "B": 17}
    assert result["series_tie"] is True
    assert result["winner_group"] is None


def test_final_result_counts_row_ties_separately_from_series_ties():
    rows = [_row(None, 0, 0), _row("A", 20, 5)]
    result = final_result(rows, "A", "B")
    assert result["ties"] == 1
    assert result["sub_games_won"] == {"A": 1, "B": 0}


def test_build_result_report_has_the_full_section_12_top_level_shape():
    rows = [_row("A", 20, 5)]
    meta = [{
        "their_github_commit": "b" * 40, "steps": 10,
        "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00",
        "audit": {"log_verified": True, "tampered": False, "result_agreed": True},
    }]
    my_identity = {"github_commit": "a" * 40, "repos": {"thief": "https://example/thief"}}
    report = build_result_report(
        "A-vs-B", "uid-1", "A", "B", my_identity, {}, rows, meta,
        {"sha256": "x", "confirmed": True}, "2026-01-01T00:00:00+00:00", "2026-01-01T00:01:00+00:00",
    )
    assert report["report_type"] == "std_v1_result"
    assert report["schema_version"] == "1.0"
    assert report["groups"] == ["A", "B"]
    assert report["sub_games"][0]["tie"] is False
    assert report["sub_games"][0]["github_commit"] == {"A": "a" * 40, "B": "b" * 40}
    assert report["final_result"]["winner_group"] == "A"
    assert report["mutual_agreement"] == {"sha256": "x", "confirmed": True}
