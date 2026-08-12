"""peer/runtime.py tests (PRD_8 §3). PeerRuntime is exercised against a
stub transport standing in for a cooperative, independently-configured
opponent -- matching the `_StubPeerTransport` pattern already proven in
test_handshake.py for negotiate/receive_control, extended here to also
answer commit_move/reveal_move by injecting a scripted opponent reveal
straight into the runtime's own RoundExchange (simulating what a real
inbound MCP call from the opponent's server thread would do). The real
two-real-process proof is the separate integration test (PRD_8 §5)."""

import json

import pytest

from thief_peer.domain.negotiation import Negotiation, canonical_terms
from thief_peer.domain.rules import has_survived
from thief_peer.exceptions import SimulationError
from thief_peer.peer.runtime import PeerRuntime
from thief_peer.peer.sealing import sealed_spec_record
from thief_peer.shared.config import ConfigManager

_GAME_JSON = """
{
  "board_and_agents": {"grid_size": 5, "num_agents": 2, "axis_origin_corner": "top-left",
                        "axis_start_index": 0, "thief_start": [2, 2], "cop_start": [0, 0]},
  "world": {"map_area": "New York", "hint_max_words": 15},
  "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                             "max_moves": 35, "survival_threshold": 3},
  "scoring": {"capture_cop": 20, "capture_thief": 5, "survival_cop": 5, "survival_thief": 10,
              "tie_score": 2, "technical_loss": 0},
  "pheromones": {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5}
}
"""


def _config(tmp_path, name="thief", port=8901):
    toml_path = tmp_path / f"{name}.toml"
    toml_path.write_text(f"[network]\nmy_port = {port}\n", encoding="utf-8")
    json_path = tmp_path / f"{name}.json"
    json_path.write_text(_GAME_JSON, encoding="utf-8")
    return ConfigManager(toml_path, json_path)


class _FakeGmailService:
    def users(self):
        return self

    def messages(self):
        return self

    def send(self, userId, body):  # noqa: N803 -- must match the real Gmail API's kwarg name
        return self

    def execute(self):
        return {"id": "fake-message-id"}


class _CooperativeStubOpponent:
    """Stands in for a real, independently-configured Cop peer that always
    answers immediately and cooperatively -- its own config, its own group
    name, exactly as `_StubPeerTransport` does for negotiate/receive_control
    in test_handshake.py."""

    def __init__(self, runtime: PeerRuntime, their_config: ConfigManager, their_group_name: str):
        self._runtime = runtime
        self._their_config = their_config
        self._their_group_name = their_group_name

    def call(self, tool_name: str, payload: dict) -> dict:
        if tool_name == "negotiate":
            return Negotiation.signed(canonical_terms(self._their_config))
        if tool_name == "receive_control" and payload.get("type") == "step0":
            return {"record": sealed_spec_record(self._their_group_name)}
        if tool_name == "commit_move":
            return {"ok": True}
        if tool_name == "reveal_move":
            step = payload["payload"]["step"]
            # Inject the opponent's own scripted reveal straight into the
            # runtime's mailbox, exactly as its real inbound MCP handler
            # would once a real server thread received it.
            self._runtime.handle_reveal_move(
                {"step": step, "sender": "cop", "hint": "closing in", "scent_grid": {}, "move": "N", "intent": "truth"}
            )
            return {"ok": True}
        if tool_name == "submit_audit":
            from thief_peer.domain.crypto import audit_records

            return audit_records(payload["payload"]["records"])
        if tool_name == "get_revealed_records":
            # A cooperative opponent has its own clean, unrevealed-until-now
            # log too -- an empty one is fine here, only the shape matters
            # for this stub; the real audit-of-a-real-log path is proven by
            # test_live_match.py's two real PeerRuntime instances.
            return {"records": []}
        raise ValueError(f"unexpected tool call: {tool_name}")


def test_a_short_match_completes_and_produces_a_clean_audit_and_report(tmp_path):
    my_config = _config(tmp_path, "mine", port=8901)
    their_config = _config(tmp_path, "theirs", port=8902)

    results_dir = tmp_path / "results"
    from thief_peer.shared.gatekeeper import ApiGatekeeper
    from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket

    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )

    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=results_dir,
        round_deadline_sec=2.0,
    )
    opponent = _CooperativeStubOpponent(runtime, their_config, their_group_name="Cop-Team")
    runtime.transport = opponent

    result = runtime.run()

    assert result["audit"]["passed"] is True
    assert has_survived(runtime.state, survival_threshold=3)
    assert len(runtime.records) >= 3
    assert (results_dir / f"result_{result['game_id']}.json").exists()
    saved_result = json.loads((results_dir / f"result_{result['game_id']}.json").read_text())
    assert "final_result" in saved_result
    assert "sha256" in saved_result["mutual_agreement"]


def test_handle_commit_move_and_reveal_move_record_into_round_exchange(tmp_path):
    my_config = _config(tmp_path, "mine", port=8903)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    runtime.handle_commit_move({"step": 1, "sender": "cop", "h_commit": "abc"})
    runtime.handle_reveal_move({"step": 1, "sender": "cop", "hint": "h", "scent_grid": {}, "move": "N", "intent": "truth"})

    assert runtime.round_exchange.wait_for_commit(1, timeout=0.1) == "abc"
    assert runtime.round_exchange.wait_for_reveal(1, timeout=0.1)["move"] == "N"


def test_handle_get_revealed_records_refuses_before_the_match_has_ended(tmp_path):
    my_config = _config(tmp_path, "mine", port=8908)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    runtime.records.append({"payload": {"state": "s", "nonce": "n"}, "commit": "c"})

    with pytest.raises(SimulationError, match="not revealed"):
        runtime.handle_get_revealed_records({})


def test_handle_get_revealed_records_returns_them_once_the_match_has_ended(tmp_path):
    my_config = _config(tmp_path, "mine", port=8909)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    runtime.records.append({"payload": {"state": "s", "nonce": "n"}, "commit": "c"})
    runtime._match_over = True

    response = runtime.handle_get_revealed_records({})

    assert response == {"records": runtime.records}


def test_handle_receive_barrier_declaration_records_a_barrier_elsewhere(tmp_path):
    my_config = _config(tmp_path, "mine", port=8910)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    response = runtime.handle_receive_barrier_declaration({"row": 0, "col": 0})

    assert response == {"ok": True}
    assert (0, 0) in runtime.state.known_barriers
    assert runtime._captured_by_barrier is False


def test_handle_receive_barrier_declaration_flags_capture_on_my_own_cell(tmp_path):
    my_config = _config(tmp_path, "mine", port=8911)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    row, col = runtime.state.position

    runtime.handle_receive_barrier_declaration({"row": row, "col": col})

    assert runtime._captured_by_barrier is True


def test_handle_receive_capture_claim_confirms_a_genuine_barrier_capture(tmp_path):
    my_config = _config(tmp_path, "mine", port=8912)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    row, col = runtime.state.position
    runtime.handle_receive_barrier_declaration({"row": row, "col": col})

    response = runtime.handle_receive_capture_claim({"reason": "barrier"})

    assert response == {"confirmed": True}


def test_handle_receive_capture_claim_denies_an_unfounded_barrier_claim(tmp_path):
    my_config = _config(tmp_path, "mine", port=8913)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    response = runtime.handle_receive_capture_claim({"reason": "barrier"})

    assert response == {"confirmed": False}


def test_handle_receive_capture_claim_confirms_a_genuine_stuck_capture(tmp_path):
    my_config = _config(tmp_path, "mine", port=8914)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    row, col = runtime.state.position
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        runtime.state.record_barrier((row + dr, col + dc))

    response = runtime.handle_receive_capture_claim({"reason": "stuck"})

    assert response == {"confirmed": True}


def test_handle_receive_capture_claim_confirms_a_genuine_landing_capture(tmp_path):
    # book Table 2 (Ch.3.5): the primary capture condition -- the Cop
    # lands directly on the Thief's cell.
    my_config = _config(tmp_path, "mine", port=8924)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    row, col = runtime.state.position

    response = runtime.handle_receive_capture_claim({"reason": "landing", "row": row, "col": col})

    assert response == {"confirmed": True}
    assert runtime._captured_by_landing is True


def test_handle_receive_capture_claim_denies_an_unfounded_landing_claim(tmp_path):
    my_config = _config(tmp_path, "mine", port=8925)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    row, col = runtime.state.position

    response = runtime.handle_receive_capture_claim(
        {"reason": "landing", "row": row + 1, "col": col}
    )

    assert response == {"confirmed": False}
    assert runtime._captured_by_landing is False


def test_handle_receive_capture_claim_denies_an_unknown_reason(tmp_path):
    my_config = _config(tmp_path, "mine", port=8915)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    response = runtime.handle_receive_capture_claim({"reason": "teleportation"})

    assert response == {"confirmed": False}


def test_being_captured_by_barrier_ends_the_match_after_the_current_round(tmp_path):
    from thief_peer.shared.gatekeeper import ApiGatekeeper
    from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket

    my_config = _config(tmp_path, "mine", port=8916)
    their_config = _config(tmp_path, "theirs", port=8917)
    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        round_deadline_sec=2.0,
    )
    opponent = _CooperativeStubOpponent(runtime, their_config, their_group_name="Cop-Team")
    runtime.transport = opponent
    runtime._captured_by_barrier = True  # simulates an inbound declaration that already arrived

    result = runtime.run()

    assert result["final_result"]["winner_group"] == "Cop-Team"
    assert len(runtime.records) == 1


def test_being_captured_by_landing_ends_the_match_after_the_current_round(tmp_path):
    from thief_peer.shared.gatekeeper import ApiGatekeeper
    from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket

    my_config = _config(tmp_path, "mine", port=8930)
    their_config = _config(tmp_path, "theirs", port=8931)
    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        round_deadline_sec=2.0,
    )
    opponent = _CooperativeStubOpponent(runtime, their_config, their_group_name="Cop-Team")
    runtime.transport = opponent
    runtime._captured_by_landing = True  # simulates an inbound capture claim that already arrived

    result = runtime.run()

    assert result["final_result"]["winner_group"] == "Cop-Team"
    assert len(runtime.records) == 1


def test_handle_negotiate_returns_my_own_signed_terms(tmp_path):
    my_config = _config(tmp_path, "mine", port=8904)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    response = runtime.handle_negotiate({"terms": {}, "nonce": "x", "commit": "y"})

    assert response["terms"] == canonical_terms(my_config)
    assert "commit" in response and "nonce" in response


def test_handle_receive_control_returns_my_own_step0_record(tmp_path):
    my_config = _config(tmp_path, "mine", port=8905)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    response = runtime.handle_receive_control({"type": "step0", "record": {}})

    assert response["record"]["payload"]["group_name"] == "Thief-Team"


def test_heartbeat_monitor_beats_during_a_real_match_and_stops_after(tmp_path):
    my_config = _config(tmp_path, "mine", port=8918)
    their_config = _config(tmp_path, "theirs", port=8919)
    from thief_peer.shared.gatekeeper import ApiGatekeeper
    from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket

    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        round_deadline_sec=2.0,
    )
    opponent = _CooperativeStubOpponent(runtime, their_config, their_group_name="Cop-Team")
    runtime.transport = opponent
    heartbeat_before_run = runtime.heartbeat.last_heartbeat

    runtime.run()

    assert runtime.heartbeat.last_heartbeat > heartbeat_before_run
    assert runtime.heartbeat.triggered is False


def test_repos_load_from_the_private_configs_repos_section(tmp_path):
    toml_path = tmp_path / "mine.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8920\n'
        '[repos]\nthief = "https://github.com/yamandahle/thief-peer"\n'
        'cop = "https://github.com/Nagham1023/yamanagh-cop"\n',
        encoding="utf-8",
    )
    json_path = tmp_path / "mine.json"
    json_path.write_text(_GAME_JSON, encoding="utf-8")
    config = ConfigManager(toml_path, json_path)
    runtime = PeerRuntime(
        config=config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    assert runtime.repos == {
        "thief": "https://github.com/yamandahle/thief-peer",
        "cop": "https://github.com/Nagham1023/yamanagh-cop",
    }


def test_repos_defaults_to_empty_dict_when_no_repos_section(tmp_path):
    my_config = _config(tmp_path, "mine", port=8921)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    assert runtime.repos == {}


class _CooperativeCopStubOpponent:
    """Stands in for a real Cop peer speaking her actual wire vocabulary --
    builds a genuinely matching declaration (same shared config file, same
    default pheromone params) so Step-0 verification legitimately passes,
    the real-match precondition `interop/cop_handshake.py` checks for."""

    def __init__(self, shared_config_path, group_name="Cop-Team"):
        self._shared_config_path = shared_config_path
        self._group_name = group_name

    def call(self, tool_name: str, payload: dict) -> dict:
        from thief_peer.domain.scent_lock import scent_lock_hash
        from thief_peer.interop.cop_wire import (
            build_cop_declaration,
            build_cop_hardware,
            current_git_commit_hash,
            hash_config_file,
            sign_cop_declaration,
        )

        if tool_name == "receive_step0":
            declaration = build_cop_declaration(
                hardware=build_cop_hardware(
                    {"os": "Linux", "cpu_cores": 4, "ram_gb": 8.0, "gpu": None, "vram_gb": None},
                    "template",
                ),
                code_commit_hash=current_git_commit_hash(),
                group_name=self._group_name,
                sub_game_number=1,
                config_sha256=hash_config_file(self._shared_config_path),
                scent_model_sha256=scent_lock_hash(0.9, 0.10, 5),
            )
            return {
                "declaration": declaration,
                "signature": sign_cop_declaration(declaration),
                "repos": {"cop": "x", "thief": "y"},
            }
        if tool_name == "receive_commit":
            return {"acknowledged": True}
        if tool_name == "receive_reveal":
            return {"accepted": True, "word_count": 1}
        if tool_name == "share_scent_map":
            return {"cells": []}
        if tool_name == "receive_final_reveal":
            return {"acknowledged": True}
        raise ValueError(f"unexpected tool call: {tool_name}")


def test_a_short_cop_v1_match_completes_using_her_wire_vocabulary(tmp_path, monkeypatch):
    # _CooperativeCopStubOpponent never calls back into this side's own
    # receive_final_reveal tool (it only answers as the opponent's client
    # role), so cop_shutdown_grace's event never fires here -- shorten the
    # ceiling so the test doesn't actually wait the real default out.
    monkeypatch.setattr("thief_peer.interop.cop_opponent.SHUTDOWN_GRACE_CEILING_SECONDS", 0.05)
    monkeypatch.setattr("thief_peer.interop.cop_opponent.RESPONSE_FLUSH_SECONDS", 0.01)
    toml_path = tmp_path / "mine.toml"
    toml_path.write_text(
        "[network]\nmy_port = 8922\nopponent_protocol = \"cop_v1\"\n", encoding="utf-8"
    )
    json_path = tmp_path / "mine.json"
    json_path.write_text(_GAME_JSON, encoding="utf-8")
    my_config = ConfigManager(toml_path, json_path)

    from thief_peer.shared.gatekeeper import ApiGatekeeper
    from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket

    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
        round_deadline_sec=2.0,
        shared_config_path=str(json_path),
    )
    runtime.transport = _CooperativeCopStubOpponent(str(json_path))

    result = runtime.run()

    assert has_survived(runtime.state, survival_threshold=3)
    assert result["final_result"]["winner_group"] == "Thief-Team"


def test_view_never_exposes_an_opponent_position_field(tmp_path):
    my_config = _config(tmp_path, "mine", port=8906)
    runtime = PeerRuntime(
        config=my_config,
        group_name="Thief-Team",
        gatekeeper=None,
        email_service=None,
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )

    view = runtime.view()

    assert view.own_position == (2, 2)
    assert not hasattr(view, "opponent_position")
