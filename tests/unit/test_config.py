"""ConfigManager v0 — private TOML loader only (PRD_1 §3/TODO_1). Shared
game.json overlay is deliberately deferred to Stage 4 (PRD_2 §2.3)."""

import pytest

from thief_peer.exceptions import ConfigError
from thief_peer.shared.config import ConfigManager


def _write_toml(path, content: str):
    path.write_text(content, encoding="utf-8")
    return path


def test_get_returns_nested_dotted_value(tmp_path):
    toml_path = _write_toml(
        tmp_path / "game.toml",
        '[network]\nmy_port = 8802\n[game]\ngroup_name = "My-Team"\n',
    )
    config = ConfigManager(toml_path)
    assert config.get("network.my_port") == 8802
    assert config.get("game.group_name") == "My-Team"


def test_get_returns_default_when_key_missing(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    config = ConfigManager(toml_path)
    assert config.get("network.opponent_url", "fallback") == "fallback"
    assert config.get("nonexistent.section") is None


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        ConfigManager(tmp_path / "does_not_exist.toml")


def test_invalid_toml_raises_config_error(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "this is not [valid toml")
    with pytest.raises(ConfigError):
        ConfigManager(toml_path)


def test_get_on_partial_path_that_is_not_a_dict_returns_default(tmp_path):
    # "network.my_port" is an int, not a dict — "network.my_port.deeper"
    # must not crash, just fall through to the default.
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    config = ConfigManager(toml_path)
    assert config.get("network.my_port.deeper", "default") == "default"


def test_require_returns_value_when_present(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    config = ConfigManager(toml_path)
    assert config.require("network.my_port") == 8802


def test_require_raises_config_error_when_missing(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    config = ConfigManager(toml_path)
    with pytest.raises(ConfigError, match="network.opponent_url"):
        config.require("network.opponent_url")


def _write_json(path, content: str):
    path.write_text(content, encoding="utf-8")
    return path


def test_json_overlay_merges_shared_terms_into_the_same_namespace(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    json_path = _write_json(
        tmp_path / "game.json", '{"board_and_agents": {"grid_size": 7}}'
    )
    config = ConfigManager(toml_path, json_path)

    assert config.get("board_and_agents.grid_size") == 7
    assert config.get("network.my_port") == 8802


def test_json_shared_terms_win_over_a_same_named_toml_key(tmp_path):
    # ADR-5: game.json is signed and shared; the private game.toml must
    # never be able to quietly "weaken" a term both sides agreed to.
    toml_path = _write_toml(tmp_path / "game.toml", "[world]\nmap_area = \"private-value\"\n")
    json_path = _write_json(tmp_path / "game.json", '{"world": {"map_area": "New York"}}')
    config = ConfigManager(toml_path, json_path)

    assert config.get("world.map_area") == "New York"


def test_json_overlay_is_optional_and_defaults_to_toml_only(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    config = ConfigManager(toml_path)
    assert config.get("board_and_agents.grid_size") is None


def test_missing_json_file_raises_config_error(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    with pytest.raises(ConfigError):
        ConfigManager(toml_path, tmp_path / "does_not_exist.json")


def test_invalid_json_raises_config_error(tmp_path):
    toml_path = _write_toml(tmp_path / "game.toml", "[network]\nmy_port = 8802\n")
    json_path = _write_json(tmp_path / "game.json", "{not valid json")
    with pytest.raises(ConfigError):
        ConfigManager(toml_path, json_path)
