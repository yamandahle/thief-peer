"""Regression test for the real starter files shipped at
`config/thief/game.toml` / `config/thief/game.json` (added once `cli.py run`
became real, Stage 8) -- confirms they actually load and satisfy every
required negotiated term, so a schema change elsewhere in the codebase
can't silently leave the shipped example broken."""

from pathlib import Path

from thief_peer.domain.negotiation import canonical_terms
from thief_peer.peer.sealing import validate_required_terms
from thief_peer.shared.config import ConfigManager

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "thief"


def test_shipped_config_files_exist():
    assert (_CONFIG_DIR / "game.toml").exists()
    assert (_CONFIG_DIR / "game.json").exists()


def test_shipped_config_files_load_and_satisfy_every_required_term():
    config = ConfigManager(_CONFIG_DIR / "game.toml", _CONFIG_DIR / "game.json")

    validate_required_terms(config)  # raises ConfigError on any missing term
    terms = canonical_terms(config)
    assert terms["grid_size"] == 7
    assert terms["move_set"] == ["N", "S", "E", "W", "STAY"]


def test_shipped_game_toml_has_the_two_fields_a_user_must_fill_in():
    config = ConfigManager(_CONFIG_DIR / "game.toml")

    assert config.require("network.my_port") == 8801
    assert config.require("network.opponent_url")
    assert config.require("email.recipient")
    assert config.require("email.token_path") == "token.json"
