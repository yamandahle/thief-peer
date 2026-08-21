"""report/report_writer.py tests (PRD_7 §2.7, §3, §5). The league counter
must survive a simulated process restart (a fresh LeagueCounter instance
pointed at the same file), not just live in memory -- lying about this
count is an explicit disqualification-level offense if caught (PRD_7 §2.7)."""

import json

from thief_peer.exceptions import ProviderError, TransportError
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


def test_total_games_played_sums_across_every_opponent(tmp_path):
    # Rule 38 / book Sec 9.2.1 (printed p.70), verified against the book's
    # own text, not guessed: the Game-Count Declaration is a league-wide
    # running total ("how many games it has played so far"), not a
    # per-opponent count -- confirmed by the book's own worked example,
    # where two teams playing each other declared *different* numbers in
    # this same field, only possible for an unqualified running total.
    counter = LeagueCounter(tmp_path / "league.json")
    counter.record_game("team-a")
    counter.record_game("team-a")
    counter.record_game("team-b")
    assert counter.total_games_played() == 3


def test_total_games_played_is_zero_for_a_brand_new_counter(tmp_path):
    counter = LeagueCounter(tmp_path / "league.json")
    assert counter.total_games_played() == 0


def test_league_counter_tracks_different_opponents_independently(tmp_path):
    counter = LeagueCounter(tmp_path / "league.json")
    counter.record_game("cop-team-a")
    counter.record_game("cop-team-a")
    counter.record_game("cop-team-b")

    assert counter.games_played_against("cop-team-a") == 2
    assert counter.games_played_against("cop-team-b") == 1


def _sub_game_entry(**overrides):
    base = {
        "sub_game_number": 1,
        "roles": {"thief": "thief", "cop-team": "cop"},
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:05:00+00:00",
        "result": "survival",
        "winner_group": "thief",
        "tie": False,
        "is_counted": True,
        "github_commit": {"thief": "abc123", "cop-team": "def456"},
        "tokens": {"thief": None, "cop-team": None},
        "score": {"thief": 1, "cop-team": 0},
        "log_files": {"thief": "log_a-vs-b_g01.json", "cop-team": "log_a-vs-b_g01.json"},
        "audit": {"log_verified": True, "peer_audit_passed": True, "tampered": False},
    }
    base.update(overrides)
    return base


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
        "sub_game_entry": _sub_game_entry(),
    }
    base.update(overrides)
    return base


class _SpyGatekeeper:
    def __init__(self):
        self.calls = []

    def execute(self, api_call, *args, **kwargs):
        self.calls.append((api_call, args, kwargs))
        return {"id": "sent"}


class _RaisingGatekeeper:
    def __init__(self, exc):
        self._exc = exc

    def execute(self, api_call, *args, **kwargs):
        raise self._exc


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


def test_write_and_send_does_not_increment_the_counter_for_an_uncounted_game(tmp_path):
    """Rule 52: uncounted warm-up games are permitted, but must never
    inflate the persisted per-opponent count a real league match relies on
    (rules 37/38 -- the declared count must stay accurate)."""
    gatekeeper = _SpyGatekeeper()
    counter = LeagueCounter(tmp_path / "league.json")
    counter.record_game("cop-team")  # one real, counted game already played

    write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        league_counter=counter,
        is_counted=False,
    )

    assert counter.games_played_against("cop-team") == 1  # unchanged
    declaration = json.loads((tmp_path / "results" / "declaration_a-vs-b.json").read_text())
    assert declaration["games_played_against_opponent"] == 1


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

    assert set(artifacts) == {"declaration", "config", "log", "result", "email_sent"}
    assert artifacts["result"]["report_type"] == "final_game_result"
    assert artifacts["result"]["final_result"]["winner_group"] == "thief"
    assert artifacts["result"]["sub_games"][0]["sub_game_number"] == 1
    assert artifacts["result"]["mutual_agreement"]["confirmed"] is True
    assert artifacts["email_sent"] is True


def test_write_and_send_still_writes_all_artifacts_when_the_gatekeeper_blocks_the_email(tmp_path):
    """Rule 33/34 (the four JSON artifacts) must not depend on rule 32's
    email step succeeding -- a real DOS-lock/queue-full/rate-limit block
    (TransportError/ProviderError, the only two types ApiGatekeeper.execute
    can raise) degrades the email step to best-effort rather than aborting
    the whole match report."""
    gatekeeper = _RaisingGatekeeper(TransportError("gatekeeper locked"))

    artifacts = write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        league_counter=LeagueCounter(tmp_path / "league.json"),
    )

    assert artifacts["email_sent"] is False
    files = sorted(p.name for p in (tmp_path / "results").iterdir())
    assert files == [
        "config_a-vs-b_g01.json",
        "declaration_a-vs-b.json",
        "log_a-vs-b_g01.json",
        "result_a-vs-b.json",
    ]


def test_write_and_send_reports_email_not_sent_on_a_provider_error_too(tmp_path):
    gatekeeper = _RaisingGatekeeper(ProviderError("Gatekeeper call failed after retries"))

    artifacts = write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        league_counter=LeagueCounter(tmp_path / "league.json"),
    )

    assert artifacts["email_sent"] is False


def test_write_and_send_does_not_swallow_an_unrelated_bug(tmp_path):
    """The narrowed except must not hide a genuine bug elsewhere in this
    call chain -- only the two exception types the real ApiGatekeeper.execute
    can actually raise are treated as a best-effort email failure."""
    import pytest

    gatekeeper = _RaisingGatekeeper(ValueError("not a gatekeeper failure"))

    with pytest.raises(ValueError):
        write_and_send(
            _match_result(),
            gatekeeper=gatekeeper,
            email_service=object(),
            recipient="grader@example.com",
            results_dir=tmp_path / "results",
            league_counter=LeagueCounter(tmp_path / "league.json"),
        )
