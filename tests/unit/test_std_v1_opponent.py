"""interop/std_v1_opponent.py tests: the PeerRuntime wiring layer.
Verifies maybe_register_std_v1_tools only activates for the std_v1
protocol, run_std_v1_series threads runtime's own collaborators
(transport, trash_talk, round_deadline_sec) through to play_series
unchanged, and write_std_v1_result writes exactly result["report"] to
the spec's own required filename."""

import json

from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1_opponent import (
    maybe_register_std_v1_tools,
    run_std_v1_series,
    write_std_v1_result,
)


class _FakeConfig:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)

    def require(self, key):
        return self._values[key]


class _FakeRuntime:
    def __init__(self, opponent_protocol, config_values=None):
        self.opponent_protocol = opponent_protocol
        self.server_app = object()
        self.config = _FakeConfig(config_values or {})
        self.group_name = "Us"
        self.repos = {"thief": "https://example/thief"}
        self.port = 8801
        self.transport = object()
        self.trash_talk = object()
        self.round_deadline_sec = 12.0


def test_maybe_register_std_v1_tools_does_nothing_for_other_protocols():
    runtime = _FakeRuntime("cop_v1")
    maybe_register_std_v1_tools(runtime)
    assert not hasattr(runtime, "_std_v1_exchange")


def test_maybe_register_std_v1_tools_stashes_an_exchange_for_std_v1(monkeypatch):
    registered = {}
    monkeypatch.setattr(
        "thief_peer.interop.std_v1_opponent.register_std_v1_tools",
        lambda mcp, exchange: registered.update(mcp=mcp, exchange=exchange),
    )
    runtime = _FakeRuntime("std_v1")

    maybe_register_std_v1_tools(runtime)

    assert isinstance(runtime._std_v1_exchange, StdExchange)
    assert registered["exchange"] is runtime._std_v1_exchange
    assert registered["mcp"] is runtime.server_app


def test_run_std_v1_series_threads_runtimes_own_collaborators_into_play_series(monkeypatch, tmp_path):
    terms_path = tmp_path / "terms.json"
    terms_path.write_text(json.dumps({
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
        "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
        "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 6,
    }), encoding="utf-8")

    captured = {}

    def fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity,
                          board_factory, state_factory, turn_handler_factory, scent_factory,
                          trash_talk, turn_deadline_sec=10.0, **kwargs):
        captured.update(
            transport=transport, exchange=exchange, my_group_id=my_group_id,
            their_group_id=their_group_id, trash_talk=trash_talk, turn_deadline_sec=turn_deadline_sec,
        )
        return {"game_id": "us-vs-them"}

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "them",
    })
    runtime._std_v1_exchange = StdExchange()

    result = run_std_v1_series(runtime)

    assert result == {"game_id": "us-vs-them"}
    assert captured["transport"] is runtime.transport
    assert captured["exchange"] is runtime._std_v1_exchange
    assert captured["trash_talk"] is runtime.trash_talk
    assert captured["turn_deadline_sec"] == 12.0
    assert captured["my_group_id"] == "us"
    assert captured["their_group_id"] == "them"


def test_write_std_v1_result_writes_only_the_report_key_to_the_spec_filename(tmp_path):
    result = {
        "game_id": "us-vs-them",
        "consensus_object": {"unused": "diagnostic-only"},
        "report": {"report_type": "std_v1_result", "game_id": "us-vs-them"},
    }

    out_path = write_std_v1_result(result, tmp_path)

    assert out_path.name == "result_us-vs-them.json"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written == {"report_type": "std_v1_result", "game_id": "us-vs-them"}
