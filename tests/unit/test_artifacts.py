"""report/artifacts.py tests -- emitted shapes match the book's own reference
implementation exactly (github.com/rmisegal/Game-P2P-Cop-Chase,
docs/sample-run/*.json)."""

from thief_peer.report.artifact_helpers import canonical_sha256, config_filename
from thief_peer.report.artifacts import build_config, build_declaration, build_log, build_result


def _own():
    return {
        "group_id": "thief-team",
        "group_name": "Thief-Team",
        "members": ["id-1"],
        "repos": {"thief": "https://example.com/t", "cop": "https://example.com/c"},
        "mcp_servers": {"thief": "http://127.0.0.1:8801/mcp", "cop": "http://127.0.0.1:8801/mcp"},
        "llm_model": "template",
        "hardware_spec": {"cpu_cores": 4, "ram_gb": 16.0},
    }


def _opponent():
    return {
        "group_id": "cop-team",
        "group_name": "Cop-Team",
        "members": ["id-2"],
        "repos": {"thief": "https://example.com/t2", "cop": "https://example.com/c2"},
        "mcp_servers": {"thief": "http://127.0.0.1:8802/mcp", "cop": "http://127.0.0.1:8802/mcp"},
        "llm_model": "claude-sonnet-5",
        "hardware_spec": {"cpu_cores": 8, "ram_gb": 32.0},
    }


def test_build_declaration_matches_pdf_requirements():
    declaration = build_declaration(
        "a-vs-b",
        "a-vs-b_g01",
        timezone="Asia/Jerusalem",
        game_started_at="2026-01-01T00:00:00+00:00",
        game_ended_at="2026-01-01T00:01:00+00:00",
        num_sub_games=1,
        max_tokens_per_game=200000,
        own=_own(),
        opponent=_opponent(),
    )

    assert declaration["schema_version"] == "1.1"
    assert declaration["declaration_type"] == "pre_game_declaration"
    assert declaration["game_id"] == "a-vs-b"
    assert declaration["links"]["declaration"] == "declaration_a-vs-b.json"
    assert declaration["links"]["config"] == "config_a-vs-b_g<NN>.json"
    assert declaration["timezone"] == "Asia/Jerusalem"
    assert declaration["groups"]["group_1"]["group_id"] == "thief-team"
    assert "hardware_spec" in declaration["groups"]["group_1"]
    assert "spec" not in declaration["groups"]["group_1"]
    assert "signature" in declaration["groups"]["group_1"]


def test_build_config_matches_pdf_requirements():
    terms = {
        "board_and_agents": {"grid_size": 7},
        "scoring": {"capture_cop": 20, "capture_thief": 5},
    }
    config = build_config(terms, "a-vs-b", "a-vs-b_g01", 1, ["cop-team", "thief-team"])

    assert config["schema_version"] == "1.1"
    assert config["agreed_between"] == ["cop-team", "thief-team"]
    assert config["board_and_agents"] == {"grid_size": 7}
    assert config["game_id"] == "a-vs-b"
    assert config["game_uid"] == "a-vs-b_g01"
    assert config["sub_game_number"] == 1
    assert config["config_name"] == config_filename("a-vs-b", 1)
    assert config["config_sha256"] == canonical_sha256(terms)
    assert "terms" not in config


def test_build_log_matches_pdf_requirements():
    records = [{"payload": {"step": 1}, "commit": "abc", "nonce": "dead"}]
    summary = {
        "sub_game_number": 1,
        "group_id": "thief-team",
        "opponent_group_id": "cop-team",
        "audit": {"passed": True, "verified_steps": 1, "failed_steps": []},
        "records": records,
    }
    log = build_log(summary, "a-vs-b", "a-vs-b_g01")

    assert log["schema_version"] == "1.1"
    assert log["game_id"] == "a-vs-b"
    assert "records" not in log["summary"]
    assert log["summary"]["group_id"] == "thief-team"
    assert log["summary"]["audit"]["passed"] is True
    assert log["records"] == records
    assert log["mutual_agreement"]["opponent_group_id"] == "cop-team"
    assert "self_audited_by_opponent" not in log


def test_build_result_matches_pdf_requirements():
    sub_games = [
        {
            "sub_game_number": 1,
            "tokens": {"thief-team": 0, "cop-team": 0},
            "audit": {"log_verified": True, "tampered": False},
        }
    ]
    aggregate = {
        "total_score": {"cop-team": 20, "thief-team": 5},
        "sub_games_won": {"cop-team": 1, "thief-team": 0},
        "ties": 0,
        "winner_group": "cop-team",
        "series_tie": False,
    }
    result = build_result(
        "a-vs-b",
        "a-vs-b_g01",
        "Asia/Jerusalem",
        ["cop-team", "thief-team"],
        sub_games,
        aggregate,
        "deadbeef",
    )

    assert result["schema_version"] == "1.1"
    assert result["report_type"] == "final_game_result"
    assert result["timezone"] == "Asia/Jerusalem"
    assert result["mutual_agreement"] == {"sha256": "deadbeef", "confirmed": True}
    assert "mutual_agreement_signature" not in result
    assert result["final_result"]["tokens_total_series"] == {"cop-team": 0, "thief-team": 0}
