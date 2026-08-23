"""peer/runtime.py's std_v1 dispatch: `network.opponent_protocol =
"std_v1"` must short-circuit PeerRuntime.run() straight into
interop/std_v1_opponent.py's own whole-series entry point, register the
std_v1 MCP tools at construction time, and never touch the native
per-round loop, negotiation, or finalize_match at all -- std_v1 builds
and writes its own result artifact via write_std_v1_result instead."""

import json

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

    def send(self, userId, body):  # noqa: N803
        return self

    def execute(self):
        return {"id": "fake-message-id"}


def _std_v1_runtime(tmp_path, monkeypatch, port=8905, extra_toml=""):
    toml_path = tmp_path / "thief.toml"
    toml_path.write_text(
        f"[network]\nmy_port = {port}\nopponent_protocol = \"std_v1\"\nopponent_group_id = \"Cop-Team\"\n"
        + extra_toml,
        encoding="utf-8",
    )
    json_path = tmp_path / "thief.json"
    json_path.write_text(_GAME_JSON, encoding="utf-8")
    config = ConfigManager(toml_path, json_path)

    registered = {}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.maybe_register_std_v1_tools",
        lambda runtime: registered.update(runtime=runtime),
    )

    gatekeeper = ApiGatekeeper(
        token_bucket=TokenBucket(capacity=5, refill_rate=1.0),
        dos_detector=DosDetector(max_calls=100, window_seconds=60),
        queue=RequestQueue(max_depth=5),
    )
    runtime = PeerRuntime(
        config=config,
        group_name="Thief-Team",
        gatekeeper=gatekeeper,
        email_service=_FakeGmailService(),
        recipient="grader@example.com",
        results_dir=tmp_path / "results",
    )
    assert registered["runtime"] is runtime  # confirms registration happened at construction time
    return runtime


def test_run_dispatches_std_v1_matches_straight_to_run_std_v1_series(tmp_path, monkeypatch):
    runtime = _std_v1_runtime(tmp_path, monkeypatch)

    native_loop_touched = {"value": False}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.run_opponent_handshake",
        lambda self: native_loop_touched.__setitem__("value", True),
    )
    monkeypatch.setattr(
        "thief_peer.peer.runtime.run_std_v1_series",
        lambda self: {
            "game_id": "us-vs-them",
            "report": {
                "report_type": "std_v1_result",
                "mutual_agreement": {"confirmed": False},
                "league": {"counted": False},
            },
        },
    )
    written = {}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.write_std_v1_result",
        lambda result, results_dir: written.update(result=result, results_dir=results_dir),
    )

    result = runtime.run()

    assert result["game_id"] == "us-vs-them"
    assert result["report"]["report_type"] == "std_v1_result"
    assert native_loop_touched["value"] is False  # native handshake/round-loop never entered
    assert written["result"] == result
    assert written["results_dir"] == runtime.results_dir


def test_run_emails_the_report_after_writing_it_for_a_std_v1_series(tmp_path, monkeypatch):
    runtime = _std_v1_runtime(tmp_path, monkeypatch, port=8907)
    monkeypatch.setattr(
        "thief_peer.peer.runtime.run_std_v1_series",
        lambda self: {
            "game_id": "us-vs-them",
            "report": {
                "report_type": "std_v1_result",
                "mutual_agreement": {"confirmed": False},
                "league": {"counted": False},
            },
        },
    )
    monkeypatch.setattr("thief_peer.peer.runtime.write_std_v1_result", lambda result, results_dir: None)

    emailed = {}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.send_std_v1_report_email",
        lambda result, runtime, *, is_counted: emailed.update(
            result=result, runtime=runtime, is_counted=is_counted
        ),
    )

    result = runtime.run()

    assert emailed["result"] == result
    assert emailed["runtime"] is runtime
    assert emailed["is_counted"] is False  # confirmed=False -> not treated as counted


class _SpyLeagueCounter:
    def __init__(self):
        self.recorded = []

    def record_game(self, opponent_group_id):
        self.recorded.append(opponent_group_id)
        return len(self.recorded)


def test_run_does_not_cc_the_lecturer_or_persist_the_league_slot_when_unconfirmed(tmp_path, monkeypatch):
    # The actual fix: an attempt run as counted (is_counted=True) that ends
    # with mutual_agreement.confirmed=False must not reach the lecturer or
    # consume the one-shot counted-game slot -- a broken/unconfirmed peer
    # must never burn a real attempt for nothing (real risk named live by
    # yanell11's own team: "both teams score zero -- we've each burned our
    # one counted game").
    runtime = _std_v1_runtime(tmp_path, monkeypatch, port=8908)
    runtime.is_counted = True
    spy_counter = _SpyLeagueCounter()

    def fake_series(self):
        self._league_counter = spy_counter
        self._their_group_id = "opponent-team"
        return {
            "game_id": "us-vs-them",
            "report": {
                "report_type": "std_v1_result",
                "mutual_agreement": {"confirmed": False},
                "league": {"counted": True},  # the attempt's own optimistic declaration
            },
        }

    monkeypatch.setattr("thief_peer.peer.runtime.run_std_v1_series", fake_series)
    monkeypatch.setattr("thief_peer.peer.runtime.write_std_v1_result", lambda result, results_dir: None)
    emailed = {}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.send_std_v1_report_email",
        lambda result, runtime, *, is_counted: emailed.update(is_counted=is_counted),
    )

    result = runtime.run()

    assert spy_counter.recorded == []  # slot never consumed
    assert emailed["is_counted"] is False  # lecturer never CC'd
    assert result["report"]["league"]["counted"] is False  # report corrected to match reality


def test_run_does_cc_the_lecturer_and_persist_the_league_slot_when_confirmed(tmp_path, monkeypatch):
    runtime = _std_v1_runtime(tmp_path, monkeypatch, port=8909)
    runtime.is_counted = True
    spy_counter = _SpyLeagueCounter()

    def fake_series(self):
        self._league_counter = spy_counter
        self._their_group_id = "opponent-team"
        return {
            "game_id": "us-vs-them",
            "report": {
                "report_type": "std_v1_result",
                "mutual_agreement": {"confirmed": True},
                "league": {"counted": True},
            },
        }

    monkeypatch.setattr("thief_peer.peer.runtime.run_std_v1_series", fake_series)
    monkeypatch.setattr("thief_peer.peer.runtime.write_std_v1_result", lambda result, results_dir: None)
    emailed = {}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.send_std_v1_report_email",
        lambda result, runtime, *, is_counted: emailed.update(is_counted=is_counted),
    )

    runtime.run()

    assert spy_counter.recorded == ["opponent-team"]
    assert emailed["is_counted"] is True


def test_run_treats_a_documented_consensus_override_as_counted_when_results_agreed(tmp_path, monkeypatch):
    # najamjad, live: their build never sends consensus_sha on the wire, so
    # `confirmed` can never become True against them -- `std_v1.
    # trust_documented_consensus` is the opt-in, per-opponent way an
    # explicit written agreement (both sides comparing their own emailed
    # settlement hash by hand) stands in for the live confirmation.
    runtime = _std_v1_runtime(
        tmp_path, monkeypatch, port=8910,
        extra_toml='\n[std_v1]\ntrust_documented_consensus = true\n',
    )
    runtime.is_counted = True
    spy_counter = _SpyLeagueCounter()

    def fake_series(self):
        self._league_counter = spy_counter
        self._their_group_id = "najamjad"
        return {
            "game_id": "us-vs-them",
            "report": {
                "report_type": "std_v1_result",
                "mutual_agreement": {"confirmed": False, "results_agreed": True},
                "league": {"counted": True},
            },
        }

    monkeypatch.setattr("thief_peer.peer.runtime.run_std_v1_series", fake_series)
    monkeypatch.setattr("thief_peer.peer.runtime.write_std_v1_result", lambda result, results_dir: None)
    emailed = {}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.send_std_v1_report_email",
        lambda result, runtime, *, is_counted: emailed.update(is_counted=is_counted),
    )

    result = runtime.run()

    assert spy_counter.recorded == ["najamjad"]
    assert emailed["is_counted"] is True
    assert result["report"]["league"]["counted"] is True
    # The wire-level confirmed flag is never rewritten -- the report still
    # tells the honest truth about what the wire exchange actually produced.
    assert result["report"]["mutual_agreement"]["confirmed"] is False


def test_run_ignores_the_documented_consensus_override_when_results_did_not_agree(tmp_path, monkeypatch):
    # Not a blanket bypass: a tamper/disagreement signal on an otherwise-
    # unconfirmed series must still block the counted slot even with the
    # override enabled.
    runtime = _std_v1_runtime(
        tmp_path, monkeypatch, port=8911,
        extra_toml='\n[std_v1]\ntrust_documented_consensus = true\n',
    )
    runtime.is_counted = True
    spy_counter = _SpyLeagueCounter()

    def fake_series(self):
        self._league_counter = spy_counter
        self._their_group_id = "najamjad"
        return {
            "game_id": "us-vs-them",
            "report": {
                "report_type": "std_v1_result",
                "mutual_agreement": {"confirmed": False, "results_agreed": False},
                "league": {"counted": True},
            },
        }

    monkeypatch.setattr("thief_peer.peer.runtime.run_std_v1_series", fake_series)
    monkeypatch.setattr("thief_peer.peer.runtime.write_std_v1_result", lambda result, results_dir: None)
    emailed = {}
    monkeypatch.setattr(
        "thief_peer.peer.runtime.send_std_v1_report_email",
        lambda result, runtime, *, is_counted: emailed.update(is_counted=is_counted),
    )

    result = runtime.run()

    assert spy_counter.recorded == []
    assert emailed["is_counted"] is False
    assert result["report"]["league"]["counted"] is False


def test_run_closes_the_transport_after_a_std_v1_series_even_though_finalize_match_is_skipped(
    tmp_path, monkeypatch
):
    runtime = _std_v1_runtime(tmp_path, monkeypatch, port=8906)
    monkeypatch.setattr(
        "thief_peer.peer.runtime.run_std_v1_series",
        lambda self: {
            "game_id": "x",
            "report": {
                "report_type": "std_v1_result",
                "mutual_agreement": {"confirmed": False},
                "league": {"counted": False},
            },
        },
    )
    monkeypatch.setattr("thief_peer.peer.runtime.write_std_v1_result", lambda result, results_dir: None)

    closed = {"value": False}

    class _FakeTransport:
        def close(self):
            closed["value"] = True

    runtime.transport = _FakeTransport()
    runtime.run()

    assert closed["value"] is True
