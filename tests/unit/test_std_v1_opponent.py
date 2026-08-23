"""interop/std_v1_opponent.py tests: the PeerRuntime wiring layer.
Verifies maybe_register_std_v1_tools only activates for the std_v1
protocol, run_std_v1_series threads runtime's own collaborators
(transport, trash_talk, round_deadline_sec) through to play_series
unchanged, write_std_v1_result writes exactly result["report"] to
the spec's own required filename, write_std_v1_declaration/write_std_v1_config
write the other two artifacts the links block promises, and
send_std_v1_report_email reuses report_writer.py's own gatekeeper-wrapped
send -- never a real Gmail call in these tests, only a fake gatekeeper/
service asserting on what was passed."""

import json
import time

from thief_peer.infra.mcp_client import McpTransport
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1_opponent import (
    maybe_register_std_v1_tools,
    run_std_v1_series,
    send_std_v1_report_email,
    std_v1_shutdown_grace,
    write_std_v1_config,
    write_std_v1_declaration,
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
        self.results_dir = "results"
        self.is_counted = True


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

    fake_report = {"groups": ["us", "them"], "final_result": {}}

    def fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity,
                          board_factory, state_factory, turn_handler_factory, scent_factory,
                          trash_talk, turn_deadline_sec=10.0, **kwargs):
        captured.update(
            transport=transport, exchange=exchange, my_group_id=my_group_id,
            their_group_id=their_group_id, trash_talk=trash_talk, turn_deadline_sec=turn_deadline_sec,
            turn_fsm_factory=kwargs.get("turn_fsm_factory"),
            games_played_including_this=kwargs.get("games_played_including_this"),
        )
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": fake_report,
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "them",
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    result = run_std_v1_series(runtime)

    assert result == {
        "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [], "report": fake_report,
    }
    assert captured["transport"] is runtime.transport
    assert captured["exchange"] is runtime._std_v1_exchange
    assert captured["trash_talk"] is runtime.trash_talk
    assert captured["turn_deadline_sec"] == 12.0
    assert captured["my_group_id"] == "us"
    assert captured["their_group_id"] == "them"
    # A fresh turn_fsm_factory is threaded through too, for the live GUI's
    # turn banner -- see series_runner.py::play_series's own docstring for
    # why it must be a per-sub-game factory rather than one shared object.
    assert callable(captured["turn_fsm_factory"])
    # A first counted match against a never-seen-before opponent -> 1.
    assert captured["games_played_including_this"] == 1
    log_path = runtime.results_dir / "log_us-vs-them-uid.json"
    assert log_path.exists()
    assert json.loads(log_path.read_text(encoding="utf-8"))["protocol"] == "std_v1"
    assert (runtime.results_dir / "declaration_us-vs-them.json").exists()
    assert (runtime.results_dir / "config_us-vs-them-uid.json").exists()


def test_run_std_v1_series_uses_the_default_consensus_ceiling_when_unconfigured(monkeypatch, tmp_path):
    terms_path = tmp_path / "terms.json"
    terms_path.write_text(json.dumps({
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
        "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
        "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
    }), encoding="utf-8")

    captured = {}

    def fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity,
                          board_factory, state_factory, turn_handler_factory, scent_factory,
                          trash_talk, turn_deadline_sec=10.0, **kwargs):
        captured["consensus_ceiling_sec"] = kwargs.get("consensus_ceiling_sec")
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "them",
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    assert captured["consensus_ceiling_sec"] == 400.0


def test_run_std_v1_series_honors_a_per_opponent_consensus_ceiling_override(monkeypatch, tmp_path):
    # najamjad, live: their consensus envelope can never pass validation
    # right now (no consensus_sha field at all), so waiting the full
    # default ceiling against them specifically is pure dead time.
    terms_path = tmp_path / "terms.json"
    terms_path.write_text(json.dumps({
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
        "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
        "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
    }), encoding="utf-8")

    captured = {}

    def fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity,
                          board_factory, state_factory, turn_handler_factory, scent_factory,
                          trash_talk, turn_deadline_sec=10.0, **kwargs):
        captured["consensus_ceiling_sec"] = kwargs.get("consensus_ceiling_sec")
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "them",
        "network_and_league.consensus_ceiling_sec": 30.0,
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    assert captured["consensus_ceiling_sec"] == 30.0


def test_run_std_v1_series_declares_first_meeting_true_for_a_never_played_opponent(monkeypatch, tmp_path):
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
        captured["first_meeting_between_groups"] = kwargs.get("first_meeting_between_groups")
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    league_path = tmp_path / "results" / "league_counter.json"
    league_path.parent.mkdir(parents=True, exist_ok=True)
    league_path.write_text(json.dumps({"moamteam": 1}), encoding="utf-8")

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "brand-new-opponent",
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    assert captured["first_meeting_between_groups"] is True


def test_run_std_v1_series_declares_first_meeting_false_for_an_already_played_opponent(monkeypatch, tmp_path):
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
        captured["first_meeting_between_groups"] = kwargs.get("first_meeting_between_groups")
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    league_path = tmp_path / "results" / "league_counter.json"
    league_path.parent.mkdir(parents=True, exist_ok=True)
    league_path.write_text(json.dumps({"already-played": 1}), encoding="utf-8")

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "already-played",
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    assert captured["first_meeting_between_groups"] is False


def test_run_std_v1_series_honors_a_declared_games_played_override(monkeypatch, tmp_path):
    # User's own explicit, deliberate call for one opponent -- overrides
    # the computed league-wide total for the wire declaration only.
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
        captured["games_played_including_this"] = kwargs.get("games_played_including_this")
        captured["counted_games_played"] = kwargs.get("counted_games_played")
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    league_path = tmp_path / "results" / "league_counter.json"
    league_path.parent.mkdir(parents=True, exist_ok=True)
    league_path.write_text(json.dumps({"moamteam": 1, "s82kma9e": 1, "ali-ahm1": 1, "najamjad": 1}), encoding="utf-8")

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "yanell11",
        "std_v1.declared_games_played_override": 1,
    })
    runtime.is_counted = True
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    assert captured["counted_games_played"] == 1
    assert captured["games_played_including_this"] == 2  # override(1) + 1, not the real total(4) + 1


def test_run_std_v1_series_leaves_police_relay_transport_none_by_default(monkeypatch, tmp_path):
    # rule 1/2 rollback safety: with no `network.cop_relay_url` configured,
    # play_series must not receive a relay transport -- every even
    # sub-game keeps using the old built-in police_brain.py stand-in
    # unchanged, exactly as it did before this feature existed.
    terms_path = tmp_path / "terms.json"
    terms_path.write_text(json.dumps({
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
        "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
        "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
    }), encoding="utf-8")

    captured = {}

    def fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity,
                          board_factory, state_factory, turn_handler_factory, scent_factory,
                          trash_talk, turn_deadline_sec=10.0, **kwargs):
        captured["police_relay_transport"] = kwargs.get("police_relay_transport")
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "them",
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    assert captured["police_relay_transport"] is None


def test_run_std_v1_series_builds_and_closes_a_relay_transport_when_configured(monkeypatch, tmp_path):
    # When `network.cop_relay_url` is set, a real McpTransport pointed at
    # it is threaded through to play_series, and closed once the series
    # finishes (mirrors how runtime.transport's own lifetime is managed
    # elsewhere -- this repo never leaves a background transport thread
    # running past the match it was built for).
    terms_path = tmp_path / "terms.json"
    terms_path.write_text(json.dumps({
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
        "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
        "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
    }), encoding="utf-8")

    captured = {}

    def fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity,
                          board_factory, state_factory, turn_handler_factory, scent_factory,
                          trash_talk, turn_deadline_sec=10.0, **kwargs):
        captured["police_relay_transport"] = kwargs.get("police_relay_transport")
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "them",
        "network.cop_relay_url": "http://127.0.0.1:8901/mcp",
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    transport = captured["police_relay_transport"]
    assert isinstance(transport, McpTransport)
    assert transport.opponent_url == "http://127.0.0.1:8901/mcp"
    assert transport._connected is False  # closed after the series, never left open


def test_run_std_v1_series_factories_sync_live_state_onto_runtime(monkeypatch, tmp_path):
    """The live GUI (gui/live_session.py polling PeerRuntime.view()) only
    shows real std_v1 play if board_factory/state_factory/turn_handler_
    factory/turn_fsm_factory each assign their object onto `runtime` as
    well as returning it to series_runner.py -- this is the one behavior
    that makes the board/belief heatmap and turn banner live instead of
    frozen at whatever `__init__` left them at."""
    terms_path = tmp_path / "terms.json"
    terms_path.write_text(json.dumps({
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
        "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
        "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
    }), encoding="utf-8")

    seen = {}

    def fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity,
                          board_factory, state_factory, turn_handler_factory, scent_factory,
                          trash_talk, turn_deadline_sec=10.0, **kwargs):
        seen["board"] = board_factory()
        seen["state"] = state_factory("thief")
        seen["turn_handler"] = turn_handler_factory(seen["board"], seen["state"])
        seen["turn_fsm"] = kwargs["turn_fsm_factory"]()
        return {
            "game_id": "us-vs-them", "game_uid": "us-vs-them-uid", "records": [],
            "report": {"groups": ["us", "them"], "final_result": {}},
        }

    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.play_series", fake_play_series)

    runtime = _FakeRuntime("std_v1", {
        "std_v1.terms_path": str(terms_path),
        "std_v1.group_id": "us",
        "network.opponent_group_id": "them",
    })
    runtime._std_v1_exchange = StdExchange()
    runtime.results_dir = tmp_path / "results"

    run_std_v1_series(runtime)

    assert runtime.board is seen["board"]
    assert runtime.state is seen["state"]
    assert runtime.turn_handler is seen["turn_handler"]
    assert runtime.turn_fsm is seen["turn_fsm"]


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


def test_write_std_v1_declaration_writes_groups_and_games_played(tmp_path):
    result = {
        "game_id": "us-vs-them", "game_uid": "us-vs-them-uid",
        "report": {"groups": ["us", "them"]},
    }
    terms = {"num_games": 6}

    out_path = write_std_v1_declaration(result, terms, tmp_path, games_played=3)

    assert out_path.name == "declaration_us-vs-them.json"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["game_id"] == "us-vs-them"
    assert written["game_uid"] == "us-vs-them-uid"
    assert written["num_sub_games"] == 6
    assert written["groups"] == ["us", "them"]
    assert written["games_played_against_opponent"] == 3


def test_write_std_v1_config_writes_the_negotiated_terms(tmp_path):
    result = {"game_uid": "us-vs-them-uid"}
    terms = {"board_size": 7, "num_games": 6}

    out_path = write_std_v1_config(result, terms, tmp_path)

    assert out_path.name == "config_us-vs-them-uid.json"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["terms"] == terms


class _FakeGatekeeper:
    def execute(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def test_send_std_v1_report_email_ccs_the_opponent_and_reaches_the_league_address_when_counted(monkeypatch):
    # Rules 9.3/35: a counted run's result must reach the fixed league
    # address automatically. The configured [email] recipient (the
    # opponent's own address for std_v1) is CC'd too, so both sides can
    # diff their filings (confirmed live: yanell11, "send a copy to
    # yanalserhan3@gmail.com so we can diff").
    sent = {}
    monkeypatch.setattr(
        "thief_peer.report.report_writer.email_sender.send_report",
        lambda service, recipient, report: sent.update(service=service, recipient=recipient, report=report),
    )
    result = {"report": {"report_type": "std_v1_result", "game_id": "us-vs-them"}}
    runtime = _FakeRuntime("std_v1")
    runtime.gatekeeper = _FakeGatekeeper()
    runtime.email_service = "fake-gmail-service"
    runtime.recipient = "opponent@example.com"
    runtime.is_counted = True

    sent_ok = send_std_v1_report_email(result, runtime, is_counted=True)

    assert sent_ok is True
    assert sent["service"] == "fake-gmail-service"
    assert sent["recipient"] == "opponent@example.com, rmisegal+uoh26finalgame@gmail.com"
    assert sent["report"] == result["report"]


def test_send_std_v1_report_email_can_suppress_the_opponent_cc_on_a_counted_send(monkeypatch):
    # Opt-in, per-opponent convention: some teams want the league address
    # as the sole recipient on a counted filing.
    sent = {}
    monkeypatch.setattr(
        "thief_peer.report.report_writer.email_sender.send_report",
        lambda service, recipient, report: sent.update(recipient=recipient),
    )
    result = {"report": {"report_type": "std_v1_result", "game_id": "us-vs-them"}}
    runtime = _FakeRuntime("std_v1", {"email.cc_opponent_on_counted_report": False})
    runtime.gatekeeper = _FakeGatekeeper()
    runtime.email_service = "fake-gmail-service"
    runtime.recipient = "opponent@example.com"

    send_std_v1_report_email(result, runtime, is_counted=True)

    assert sent["recipient"] == "rmisegal+uoh26finalgame@gmail.com"


def test_send_std_v1_report_email_keeps_ccing_the_opponent_by_default_when_counted(monkeypatch):
    # The flag is opt-in -- every existing config that never sets it keeps
    # today's behavior (opponent CC'd alongside the league address).
    sent = {}
    monkeypatch.setattr(
        "thief_peer.report.report_writer.email_sender.send_report",
        lambda service, recipient, report: sent.update(recipient=recipient),
    )
    result = {"report": {"report_type": "std_v1_result", "game_id": "us-vs-them"}}
    runtime = _FakeRuntime("std_v1")
    runtime.gatekeeper = _FakeGatekeeper()
    runtime.email_service = "fake-gmail-service"
    runtime.recipient = "opponent@example.com"

    send_std_v1_report_email(result, runtime, is_counted=True)

    assert sent["recipient"] == "opponent@example.com, rmisegal+uoh26finalgame@gmail.com"


def test_send_std_v1_report_email_sends_to_the_configured_recipient_when_not_counted(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        "thief_peer.report.report_writer.email_sender.send_report",
        lambda service, recipient, report: sent.update(service=service, recipient=recipient, report=report),
    )
    result = {"report": {"report_type": "std_v1_result", "game_id": "us-vs-them"}}
    runtime = _FakeRuntime("std_v1")
    runtime.gatekeeper = _FakeGatekeeper()
    runtime.email_service = "fake-gmail-service"
    runtime.recipient = "lecturer@example.com"
    runtime.is_counted = False

    sent_ok = send_std_v1_report_email(result, runtime, is_counted=False)

    assert sent_ok is True
    assert sent["recipient"] == "lecturer@example.com"


def test_std_v1_shutdown_grace_actually_holds_for_the_configured_duration(monkeypatch):
    # Real bug found live against moamteam: this side's server used to tear
    # down the instant run() returned, with no equivalent to
    # cop_opponent.py's own cop_shutdown_grace -- an in-flight final call
    # from the peer could land against an already-dead server. Confirms
    # the hold is real (not a no-op), via a shortened duration so this test
    # doesn't actually wait the real 20s.
    monkeypatch.setattr("thief_peer.interop.std_v1_opponent.STD_V1_SHUTDOWN_GRACE_SECONDS", 0.05)
    started = time.monotonic()

    std_v1_shutdown_grace()

    assert time.monotonic() - started >= 0.05
