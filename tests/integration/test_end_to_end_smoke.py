"""Stage 7 end-to-end smoke test (TODO_7 §5): a full scripted match wired
through Stages 1-6 (board/state/brain/belief, sealed Commit-Reveal chain,
game identifiers), then this stage's report-writer -- proving all seven
stages actually compose, not just pass in isolation.

`test_a_real_persisted_log_replays_and_verifies_end_to_end` (PRD_10, rule 20
[FATAL]) closes the loop the smoke test above stops short of: proving the
exact file `write_and_send` puts on disk is genuinely consumable by
`sdk.py::run_replay`, not just structurally similar to what
`gui/replay_view.py` expects.
"""

import json

from thief_peer.domain.board import Board
from thief_peer.domain.crypto import audit_records
from thief_peer.domain.game_ids import derive_game_id, derive_game_uid
from thief_peer.domain.own_state import OwnGameState
from thief_peer.peer.sealing import sealed_step_record
from thief_peer.peer.turn_handler import TurnHandler
from thief_peer.report.report_writer import LeagueCounter, write_and_send
from thief_peer.sdk.sdk import run_replay
from thief_peer.shared.gatekeeper import ApiGatekeeper
from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket
from thief_peer.strategy.fleeing_brain import ThiefBrain

_SCRIPTED_SCENT_FEED = [{"0,0": 0.9}, {"0,1": 0.62}, {"1,1": 0.42}]


class _FakeGmailService:
    """Just enough of the Gmail API surface for email_sender.send_report to
    complete without raising -- exercised here for wiring, not for real
    Gmail behavior (see infra/email_sender.py's own dedicated tests)."""

    def users(self):
        return self

    def messages(self):
        return self

    def send(self, userId, body):  # noqa: N803 -- must match the real Gmail API's kwarg name
        return self

    def execute(self):
        return {"id": "smoke-test-message-id"}


def test_a_full_scripted_match_produces_all_four_artifacts_and_sends_one_email(tmp_path):
    # --- Stages 1/3/4: play a short scripted match ---
    board = Board(size=9, barriers=set())
    state = OwnGameState(position=(4, 4))
    handler = TurnHandler(board, state, ThiefBrain())

    records = []
    for step, scent_snapshot in enumerate(_SCRIPTED_SCENT_FEED, start=1):
        decision = handler.play_turn(scent_snapshot)
        move = decision.direction.value if decision.direction else "STAY"
        # --- Stage 6: seal each step into the audited commit chain ---
        records.append(
            sealed_step_record(
                state=f"step-{step}",
                move=move,
                intent="truth",
                hint_text="",
                step=step,
                role="thief",
            )
        )

    audit = audit_records(records)
    assert audit["passed"] is True

    game_id = derive_game_id("thief-team", "cop-team")
    game_uid = derive_game_uid(game_id, sub_game_number=1)

    match_result = {
        "game_id": game_id,
        "game_uid": game_uid,
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
        "shared_config_terms": {"board_and_agents": {"grid_size": 9}},
        "log_summary": {
            "sub_game_number": 1,
            "group_id": "thief-team",
            "role": "thief",
            "opponent_group_id": "cop-team",
            "result": "survival",
            "winner_role": "thief",
            "steps": len(records),
            "started_at": "2026-01-01T00:00:00+00:00",
            "duration_seconds": 60.0,
            "tokens_total": 0,
            "audit": audit,
            "records": records,
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
        "mutual_sha256": "smoke-test-sha",
    }

    # --- Stage 7: report the match ---
    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )
    results_dir = tmp_path / "results"

    artifacts = write_and_send(
        match_result,
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=results_dir,
        league_counter=LeagueCounter(tmp_path / "league.json"),
    )

    # All four artifacts landed on disk, sharing the same game_id/game_uid.
    files = sorted(p.name for p in results_dir.iterdir())
    assert files == [
        f"config_{game_id}_g01.json",
        f"declaration_{game_id}.json",
        f"log_{game_id}_g01.json",
        f"result_{game_id}.json",
    ]
    declaration = json.loads((results_dir / f"declaration_{game_id}.json").read_text())
    assert declaration["game_uid"] == game_uid
    assert declaration["schema_version"] == "1.1"
    log = json.loads((results_dir / f"log_{game_id}_g01.json").read_text())
    assert log["summary"]["audit"]["passed"] is True
    assert len(log["records"]) == len(_SCRIPTED_SCENT_FEED)

    outcomes = [entry["outcome"] for entry in gatekeeper.call_log]
    assert outcomes == ["success"]

    assert artifacts["result"]["final_result"]["winner_group"] == "thief-team"


def _play_and_write_log(tmp_path):
    """Mirrors the scripted match above, returning just the persisted
    log file's path -- the piece `run_replay` actually reads."""
    board = Board(size=9, barriers=set())
    state = OwnGameState(position=(4, 4))
    handler = TurnHandler(board, state, ThiefBrain())

    records = []
    for step, scent_snapshot in enumerate(_SCRIPTED_SCENT_FEED, start=1):
        decision = handler.play_turn(scent_snapshot)
        move = decision.direction.value if decision.direction else "STAY"
        records.append(
            sealed_step_record(
                state=f"step-{step}", move=move, intent="truth", hint_text="", step=step, role="thief"
            )
        )

    game_id = derive_game_id("thief-team", "cop-team")
    game_uid = derive_game_uid(game_id, sub_game_number=1)
    audit = audit_records(records)
    match_result = {
        "game_id": game_id,
        "game_uid": game_uid,
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
        "shared_config_terms": {"board_and_agents": {"grid_size": 9}},
        "log_summary": {
            "sub_game_number": 1,
            "group_id": "thief-team",
            "role": "thief",
            "opponent_group_id": "cop-team",
            "result": "survival",
            "winner_role": "thief",
            "steps": len(records),
            "started_at": "2026-01-01T00:00:00+00:00",
            "duration_seconds": 60.0,
            "tokens_total": 0,
            "audit": audit,
            "records": records,
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
        "mutual_sha256": "replay-smoke-sha",
    }
    results_dir = tmp_path / "results"
    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )
    write_and_send(
        match_result,
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=results_dir,
        league_counter=LeagueCounter(tmp_path / "league.json"),
    )
    return results_dir / f"log_{game_uid}.json"


def test_a_real_persisted_log_replays_and_verifies_end_to_end(tmp_path, capsys):
    log_path = _play_and_write_log(tmp_path)

    exit_code = run_replay(str(log_path))

    assert exit_code == 0
    assert "Overall: Verified OK" in capsys.readouterr().out


def test_a_tampered_persisted_log_fails_replay_end_to_end(tmp_path, capsys):
    log_path = _play_and_write_log(tmp_path)
    log = json.loads(log_path.read_text(encoding="utf-8"))
    original_move = log["records"][1]["payload"]["move"]
    # Pick any direction different from what was actually sealed -- the
    # scripted brain's real choice isn't fixed ahead of time, so "corrupt
    # to a hardcoded string" could accidentally be a no-op.
    log["records"][1]["payload"]["move"] = next(
        d for d in ["N", "S", "E", "W", "STAY"] if d != original_move
    )
    log_path.write_text(json.dumps(log), encoding="utf-8")

    exit_code = run_replay(str(log_path))

    assert exit_code == 1
    assert "Overall: TAMPERED" in capsys.readouterr().out
