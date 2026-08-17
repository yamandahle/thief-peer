from thief_peer.interop.std_v1.report import build_result_report, final_result, group_details, valid_commit

MY_GROUP = "thief-team"
THEIR_GROUP = "dev-team"


def test_valid_commit_accepts_only_exactly_40_hex_chars():
    assert valid_commit("a" * 40) == "a" * 40
    assert valid_commit("a" * 39) == ""
    assert valid_commit("g" * 40) == ""
    assert valid_commit(None) == ""
    assert valid_commit(12345) == ""


def test_group_details_extracts_the_report_only_fields():
    identity = {
        "group_id": MY_GROUP, "members": ["Alice"], "repos": {"thief": "url"},
        "mcp_servers": {"thief": "url"}, "llm_model": "template", "spec": {"os": "Windows"},
    }
    details = group_details(identity)
    assert details == {
        "group_id": MY_GROUP, "members": ["Alice"], "repos": {"thief": "url"},
        "mcp_servers": {"thief": "url"}, "llm_model": "template", "hardware_spec": {"os": "Windows"},
    }


def test_final_result_sums_scores_and_applies_tie_bonus_once_on_equal_totals():
    rows = [
        {"score": {MY_GROUP: 10, THEIR_GROUP: 5}, "winner_group": MY_GROUP},
        {"score": {MY_GROUP: 5, THEIR_GROUP: 10}, "winner_group": THEIR_GROUP},
    ]
    result = final_result(rows, MY_GROUP, THEIR_GROUP)
    assert result["total_score"] == {MY_GROUP: 17, THEIR_GROUP: 17}
    assert result["series_tie"] is True
    assert result["winner_group"] is None
    assert result["sub_games_won"] == {MY_GROUP: 1, THEIR_GROUP: 1}
    assert result["ties"] == 0


def test_final_result_no_bonus_when_totals_differ():
    rows = [
        {"score": {MY_GROUP: 20, THEIR_GROUP: 5}, "winner_group": MY_GROUP},
        {"score": {MY_GROUP: 0, THEIR_GROUP: 0}, "winner_group": None},
    ]
    result = final_result(rows, MY_GROUP, THEIR_GROUP)
    assert result["total_score"] == {MY_GROUP: 20, THEIR_GROUP: 5}
    assert result["series_tie"] is False
    assert result["winner_group"] == MY_GROUP
    assert result["ties"] == 1


def test_build_result_report_shapes_a_full_section_12_report():
    my_identity = {
        "group_id": MY_GROUP, "github_commit": "a" * 40, "members": ["Alice"],
        "repos": {"thief": "url1"}, "mcp_servers": {"thief": "url1"}, "llm_model": "template", "spec": {},
    }
    their_identity = {
        "group_id": THEIR_GROUP, "github_commit": "b" * 40, "members": ["Bob"],
        "repos": {"cop": "url2"}, "mcp_servers": {"cop": "url2"}, "llm_model": "claude", "spec": {},
    }
    rows = [
        {"sub_game_number": 1, "result": "survival", "roles": {MY_GROUP: "thief", THEIR_GROUP: "police"},
         "score": {MY_GROUP: 10, THEIR_GROUP: 5}, "winner_group": MY_GROUP},
    ]
    sub_game_meta = [{
        "their_github_commit": "b" * 40, "steps": 35, "started_at": "t0", "ended_at": "t1",
        "audit": {"log_verified": True, "tampered": False, "result_agreed": True},
    }]
    mutual_agreement = {
        "sha256": "x", "peer_sha256": "x", "sha_match": True, "results_agreed": True, "confirmed": True,
    }

    report = build_result_report(
        "dev-team-vs-thief-team", "uid-1", MY_GROUP, THEIR_GROUP, my_identity, their_identity,
        rows, sub_game_meta, mutual_agreement, "start", "end",
    )

    assert report["game_id"] == "dev-team-vs-thief-team"
    assert report["groups"] == [MY_GROUP, THEIR_GROUP]
    row = report["sub_games"][0]
    assert row["tie"] is False
    assert row["github_commit"] == {MY_GROUP: "a" * 40, THEIR_GROUP: "b" * 40}
    assert row["steps"] == 35
    assert report["links"]["github"][MY_GROUP] == {"thief": "url1"}
    assert report["group_details"][THEIR_GROUP]["members"] == ["Bob"]
    assert report["mutual_agreement"] == mutual_agreement
    assert report["final_result"]["winner_group"] == MY_GROUP
