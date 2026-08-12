"""report/report_writer.py tests (PRD_7 §2.7)."""

import json

from thief_peer.exceptions import TransportError
from thief_peer.report.report_writer import LeagueCounter, write_and_send


def _match_result(**overrides):
    base = {
        "game_id": "a-vs-b",
        "game_uid": "a-vs-b_g01",
        "sub_game_number": 1,
        "num_sub_games": 1,
        "group_ids": ["cop-team", "thief-team"],
        "timezone": "Asia/Jerusalem",
        "game_started_at": "2026-01-01T00:00:00+00:00",
        "game_ended_at": "2026-01-01T00:01:00+00:00",
        "max_tokens_per_game": 200000,
        "own": {
            "group_id": "thief-team",
            "group_name": "Thief-Team",
            "members": [],
            "repos": {},
            "mcp_servers": {},
            "llm_model": "template",
            "hardware_spec": {},
        },
        "opponent": {
            "group_id": "cop-team",
            "group_name": "Cop-Team",
            "members": [],
            "repos": {},
            "mcp_servers": {},
            "llm_model": "template",
            "hardware_spec": {},
        },
        "shared_config_terms": {"board_and_agents": {"grid_size": 7}},
        "log_summary": {
            "sub_game_number": 1,
            "group_id": "thief-team",
            "role": "thief",
            "opponent_group_id": "cop-team",
            "result": "survival",
            "winner_role": "thief",
            "steps": 1,
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": "2026-01-01T00:01:00+00:00",
            "duration_seconds": 60.0,
            "tokens_total": 0,
            "audit": {"passed": True, "verified_steps": 1, "failed_steps": []},
            "records": [{"payload": {"step": 1}, "commit": "abc", "nonce": "n"}],
        },
        "sub_games": [
            {
                "sub_game_number": 1,
                "tokens": {"thief-team": 0, "cop-team": 0},
                "audit": {"log_verified": True, "tampered": False},
            }
        ],
        "final_result_aggregate": {
            "total_score": {"thief-team": 10, "cop-team": 5},
            "sub_games_won": {"thief-team": 1, "cop-team": 0},
            "ties": 0,
            "winner_group": "thief-team",
            "series_tie": False,
        },
        "mutual_sha256": "abc123",
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
    write_and_send(
        _match_result(),
        gatekeeper=_SpyGatekeeper(),
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    files = sorted(p.name for p in (tmp_path / "results").iterdir())
    assert files == [
        "config_a-vs-b_g01.json",
        "declaration_a-vs-b.json",
        "log_a-vs-b_g01.json",
        "result_a-vs-b.json",
    ]


def test_write_and_send_emits_template_shapes_without_extra_keys(tmp_path):
    write_and_send(
        _match_result(),
        gatekeeper=_SpyGatekeeper(),
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    declaration = json.loads((tmp_path / "results" / "declaration_a-vs-b.json").read_text())
    result = json.loads((tmp_path / "results" / "result_a-vs-b.json").read_text())

    assert declaration["schema_version"] == "1.1"
    assert "games_played_against_opponent" not in declaration
    assert "timestamp" not in declaration
    assert result["schema_version"] == "1.1"
    assert "mutual_agreement_signature" not in result


def test_write_and_send_calls_send_report_bundle_with_four_attachments(tmp_path):
    gatekeeper = _SpyGatekeeper()
    write_and_send(
        _match_result(),
        gatekeeper=gatekeeper,
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    api_call, args, _kwargs = gatekeeper.calls[0]
    assert api_call.__name__ == "send_report_bundle"
    assert len(args[2]) == 4


def test_league_counter_persists_across_restarts(tmp_path):
    counter = LeagueCounter(tmp_path / "league.json")
    counter.record_game("cop-team")
    assert LeagueCounter(tmp_path / "league.json").games_played_against("cop-team") == 1


def test_write_and_send_still_writes_artifacts_when_email_fails(tmp_path):
    write_and_send(
        _match_result(),
        gatekeeper=_RaisingGatekeeper(TransportError("locked")),
        email_service=object(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    assert len(list((tmp_path / "results").iterdir())) == 4


def test_write_and_send_does_not_swallow_unrelated_bugs(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        write_and_send(
            _match_result(),
            gatekeeper=_RaisingGatekeeper(ValueError("bug")),
            email_service=object(),
            recipient="grader@example.com",
            results_dir=tmp_path / "results",
        )
