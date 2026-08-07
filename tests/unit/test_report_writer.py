"""report/report_writer.py tests (PRD_7 §2.7, §3, §5). The league counter
must survive a simulated process restart (a fresh LeagueCounter instance
pointed at the same file), not just live in memory -- lying about this
count is an explicit disqualification-level offense if caught (PRD_7 §2.7)."""

import json

from thief_peer.report.report_writer import LeagueCounter, write_and_send


def test_league_counter_starts_at_zero_for_a_new_opponent(tmp_path):
    counter = LeagueCounter(tmp_path / "league.json")
    assert counter.games_played_against("cop-team") == 0


def test_league_counter_increments_on_each_recorded_game(tmp_path):
    counter = LeagueCounter(tmp_path / "league.json")
    assert counter.record_game("cop-team") == 1
    assert counter.record_game("cop-team") == 2
    assert counter.games_played_against("cop-team") == 2


def test_league_counter_survives_a_simulated_process_restart(tmp_path):
    path = tmp_path / "league.json"
    LeagueCounter(path).record_game("cop-team")
    LeagueCounter(path).record_game("cop-team")

    fresh_instance = LeagueCounter(path)  # simulates a new process
    assert fresh_instance.games_played_against("cop-team") == 2


def test_league_counter_tracks_different_opponents_independently(tmp_path):
    counter = LeagueCounter(tmp_path / "league.json")
    counter.record_game("cop-team-a")
    counter.record_game("cop-team-a")
    counter.record_game("cop-team-b")

    assert counter.games_played_against("cop-team-a") == 2
    assert counter.games_played_against("cop-team-b") == 1


def _match_result(**overrides):
    base = {
        "game_id": "a-vs-b",
        "game_uid": "a-vs-b_g01",
        "sub_game_number": 1,
        "num_sub_games": 1,
        "opponent_group_id": "cop-team",
        "groups": {"group_1": {"identity": "thief"}},
        "shared_terms": {"grid_size": 7},
        "config_name": "config_dev_g01",
        "records": [{"payload": {"state": "s"}, "commit": "abc"}],
        "audit": {"passed": True, "verified_steps": 1, "failed_steps": []},
        "final_result": {"winner_group": "thief", "tokens_total_series": 100},
    }
    base.update(overrides)
    return base


class _SpyGatekeeper:
    def __init__(self):
        self.calls = []

    def execute(self, api_call, *args, **kwargs):
        self.calls.append((api_call, args, kwargs))
        return {"id": "sent"}


def test_write_and_send_creates_all_four_artifact_files_on_disk(tmp_path):
    gatekeeper = _SpyGatekeeper()
    write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        league_counter=LeagueCounter(tmp_path / "league.json"),
    )

    files = sorted(p.name for p in (tmp_path / "results").iterdir())
    assert files == [
        "config_a-vs-b_g01.json",
        "declaration_a-vs-b.json",
        "log_a-vs-b_g01.json",
        "result_a-vs-b.json",
    ]


def test_write_and_send_includes_the_league_counter_in_the_declaration(tmp_path):
    gatekeeper = _SpyGatekeeper()
    counter = LeagueCounter(tmp_path / "league.json")
    counter.record_game("cop-team")  # one prior game already played

    write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        league_counter=counter,
    )

    declaration = json.loads((tmp_path / "results" / "declaration_a-vs-b.json").read_text())
    assert declaration["games_played_against_opponent"] == 2


def test_write_and_send_calls_the_gatekeeper_exactly_once_with_send_report(tmp_path):
    gatekeeper = _SpyGatekeeper()
    write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        league_counter=LeagueCounter(tmp_path / "league.json"),
    )

    assert len(gatekeeper.calls) == 1
    api_call, args, kwargs = gatekeeper.calls[0]
    assert api_call.__name__ == "send_report"
    assert args[1] == "grader@example.com"


def test_write_and_send_returns_the_four_assembled_artifacts(tmp_path):
    gatekeeper = _SpyGatekeeper()
    artifacts = write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        league_counter=LeagueCounter(tmp_path / "league.json"),
    )

    assert set(artifacts) == {"declaration", "config", "log", "result"}
    assert artifacts["result"]["final_result"]["winner_group"] == "thief"
