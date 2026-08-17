"""interop/std_v1_opponent.py tests -- config-driven wiring, checked
against a real ConfigManager (a tmp TOML file) rather than a hand-rolled
stub, plus a monkeypatched play_series to inspect what it was actually
called with."""

import json
from types import SimpleNamespace

from fastmcp import FastMCP

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.scent import ScentField
from thief_peer.interop import std_v1_opponent
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.terms import load_terms
from thief_peer.peer.turn_handler import TurnHandler
from thief_peer.shared.config import ConfigManager

TERMS = load_terms()


def _write_config(tmp_path) -> ConfigManager:
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        """
[network]
opponent_group_id = "dev-team"

[std_v1]
group_id = "thief-team"
members = ["Alice"]
""",
        encoding="utf-8",
    )
    return ConfigManager(toml_path)


def test_maybe_register_std_v1_tools_is_a_noop_for_other_protocols():
    runtime = SimpleNamespace(opponent_protocol="native", server_app=None)
    std_v1_opponent.maybe_register_std_v1_tools(runtime)
    assert not hasattr(runtime, "_std_v1_exchange")


def test_maybe_register_std_v1_tools_registers_for_std_v1():
    runtime = SimpleNamespace(opponent_protocol="std_v1", server_app=FastMCP(name="test"))
    std_v1_opponent.maybe_register_std_v1_tools(runtime)
    assert isinstance(runtime._std_v1_exchange, StdExchange)


def test_run_std_v1_series_builds_group_ids_and_identity_from_config(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    captured = {}

    def _fake_play_series(transport, exchange, terms, my_group_id, their_group_id, identity, *factories, **kwargs):
        captured["terms"] = terms
        captured["my_group_id"] = my_group_id
        captured["their_group_id"] = their_group_id
        captured["identity"] = identity
        captured["factories"] = factories
        captured["kwargs"] = kwargs
        return {"agreed": True}

    monkeypatch.setattr(std_v1_opponent, "play_series", _fake_play_series)

    runtime = SimpleNamespace(
        config=config, group_name="thief-team-display", repos={"thief": "url1", "cop": "url2"},
        port=8801, round_deadline_sec=10.0, transport=object(), _std_v1_exchange=object(),
    )

    result = std_v1_opponent.run_std_v1_series(runtime)

    assert result == {"agreed": True}
    assert captured["terms"] == TERMS
    assert captured["my_group_id"] == "thief-team"
    assert captured["their_group_id"] == "dev-team"
    assert captured["identity"]["group_id"] == "thief-team"
    assert captured["identity"]["group_name"] == "thief-team-display"
    assert captured["identity"]["members"] == ["Alice"]
    assert captured["identity"]["repos"] == {"thief": "url1", "cop": "url2"}
    assert captured["kwargs"] == {"turn_deadline_sec": 10.0}


def test_run_std_v1_series_group_id_defaults_to_group_name(tmp_path, monkeypatch):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text('[network]\nopponent_group_id = "dev-team"\n', encoding="utf-8")
    config = ConfigManager(toml_path)
    captured = {}
    monkeypatch.setattr(
        std_v1_opponent, "play_series",
        lambda *a, **k: captured.update(my_group_id=a[3]) or {"agreed": True},
    )
    runtime = SimpleNamespace(
        config=config, group_name="thief-team-display", repos={},
        port=8801, round_deadline_sec=10.0, transport=object(), _std_v1_exchange=object(),
    )

    std_v1_opponent.run_std_v1_series(runtime)

    assert captured["my_group_id"] == "thief-team-display"


def test_run_std_v1_series_factories_produce_correctly_shaped_objects(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    captured = {}
    monkeypatch.setattr(
        std_v1_opponent, "play_series",
        lambda *a, **k: captured.update(factories=a[6:10]) or {"agreed": True},
    )
    runtime = SimpleNamespace(
        config=config, group_name="thief-team-display", repos={},
        port=8801, round_deadline_sec=10.0, transport=object(), _std_v1_exchange=object(),
    )

    std_v1_opponent.run_std_v1_series(runtime)
    board_factory, state_factory, turn_handler_factory, scent_factory = captured["factories"]

    board = board_factory()
    assert isinstance(board, Board)
    assert board.size == TERMS["board_size"]

    state = state_factory("thief")
    assert isinstance(state, OwnGameState)
    assert state.position == tuple(TERMS["thief_start"])

    police_state = state_factory("police")
    assert police_state.position == tuple(TERMS["cop_start"])

    scent = scent_factory()
    assert isinstance(scent, ScentField)

    handler = turn_handler_factory(board, state)
    assert isinstance(handler, TurnHandler)
    assert handler.board is board
    assert handler.state is state


def test_write_std_v1_result_writes_the_result_json(tmp_path):
    result = {"game_id": "dev-team-vs-thief-team", "agreed": True}
    out_path = std_v1_opponent.write_std_v1_result(result, tmp_path)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == result
