"""Stage 8 integration test (PRD_8 §5): the real, non-mocked proof of
Stage 8's "Done" milestone -- two independent, real `PeerRuntime` instances,
each with its own real FastMCP server and its own outbound `McpTransport`,
play a full match to completion over live localhost sockets: handshake,
every round's commit/reveal, the end-of-match mutual audit, and each side's
own JSON report artifacts landing on disk.

Note on realism: this repo has no Cop-peer implementation (the Cop is a
separate, independently-built repo per the book's hard "zero shared code"
rule) -- both sides here are real `PeerRuntime` (Thief) instances pointed at
each other. That's a deliberate, honestly-labelled proxy for proving the
*protocol/orchestration* machinery (FSM, commit/reveal wire messages,
mutual audit, reporting) actually works end to end over real sockets; it is
not a claim that this constitutes real Cop-vs-Thief gameplay.
"""

import socket
import threading

from thief_peer.peer.runtime import PeerRuntime
from thief_peer.shared.config import ConfigManager
from thief_peer.shared.gatekeeper import ApiGatekeeper
from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket

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


class _FakeGmailService:
    def users(self):
        return self

    def messages(self):
        return self

    def send(self, userId, body):  # noqa: N803 -- must match the real Gmail API's kwarg name
        return self

    def execute(self):
        return {"id": "fake-message-id"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def _gatekeeper() -> ApiGatekeeper:
    return ApiGatekeeper(
        token_bucket=TokenBucket(capacity=10, refill_rate=5.0),
        dos_detector=DosDetector(max_calls=200, window_seconds=60),
        queue=RequestQueue(max_depth=10),
    )


def _make_peer(tmp_path, name: str, my_port: int, opponent_port: int) -> PeerRuntime:
    shared_json = tmp_path / "game.json"
    if not shared_json.exists():
        shared_json.write_text(_GAME_JSON, encoding="utf-8")

    toml_path = tmp_path / f"{name}.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {my_port}\nopponent_url = "http://127.0.0.1:{opponent_port}/mcp"\n',
        encoding="utf-8",
    )
    config = ConfigManager(toml_path, shared_json)

    return PeerRuntime(
        config=config,
        group_name=f"Thief-Team-{name.upper()}",
        gatekeeper=_gatekeeper(),
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=tmp_path / f"results_{name}",
        round_deadline_sec=10.0,
    )


def test_two_real_peer_runtimes_play_a_full_match_to_completion(tmp_path):
    port_a, port_b = _free_port(), _free_port()
    runtime_a = _make_peer(tmp_path, "a", port_a, port_b)
    runtime_b = _make_peer(tmp_path, "b", port_b, port_a)

    results: dict[str, dict] = {}

    def _run_b():
        results["b"] = runtime_b.run()

    thread_b = threading.Thread(target=_run_b, daemon=True)
    thread_b.start()
    results["a"] = runtime_a.run()
    thread_b.join(timeout=60)

    assert "b" in results, "peer B's run() never completed"
    assert results["a"]["audit"]["passed"] is True
    assert results["b"]["audit"]["passed"] is True
    assert results["a"]["game_uid"] == results["b"]["game_uid"]

    # Mutual audit (rules 19/36): each side must have both submitted itself
    # for audit AND actively pulled + verified the other's revealed log --
    # not just one direction. Real records from real get_revealed_records
    # calls against each other, not stubs.
    for result in (results["a"], results["b"]):
        assert result["audit"]["self_audited_by_opponent"]["passed"] is True
        assert result["audit"]["opponent_audited_by_me"]["passed"] is True
        assert result["audit"]["opponent_audited_by_me"]["verified_steps"] >= 3

    assert runtime_a.turn_fsm.state == "WAITING_FOR_OPPONENT"
    assert runtime_b.turn_fsm.state == "WAITING_FOR_OPPONENT"

    assert len(runtime_a.records) >= 3
    assert len(runtime_b.records) >= 3

    result_file_a = tmp_path / "results_a" / f"result_{results['a']['game_id']}.json"
    result_file_b = tmp_path / "results_b" / f"result_{results['b']['game_id']}.json"
    assert result_file_a.exists()
    assert result_file_b.exists()
