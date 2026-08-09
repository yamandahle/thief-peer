"""interop/cop_handshake.py tests. `_StubCopTransport` mimics her real
`_on_step0_received` responder behavior (`orchestrator_step0.py`): builds
its own declaration/signature the same way, so this proves the exchange
genuinely works two-sided, not just that our own half is internally
consistent."""

import pytest

from thief_peer.domain.scent_lock import scent_lock_hash
from thief_peer.exceptions import ConfigError
from thief_peer.interop.cop_handshake import cop_step0_handshake
from thief_peer.interop.cop_wire import (
    build_cop_declaration,
    build_cop_hardware,
    sign_cop_declaration,
)
from thief_peer.shared.config import ConfigManager

_GAME_JSON = """
{
  "board_and_agents": {"grid_size": 7, "num_agents": 2, "axis_origin_corner": "top-left",
                        "axis_start_index": 0, "thief_start": [3, 3], "cop_start": [0, 0]},
  "world": {"map_area": "New York", "hint_max_words": 15},
  "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                             "max_moves": 35, "survival_threshold": 35},
  "scoring": {"capture_cop": 20, "capture_thief": 5, "survival_cop": 5, "survival_thief": 10,
              "tie_score": 2, "technical_loss": 0},
  "pheromones": {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5}
}
"""


def _config_and_path(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text("[network]\nmy_port = 8802\n[llm]\nmodel = \"template\"\n", encoding="utf-8")
    json_path = tmp_path / "game.json"
    json_path.write_text(_GAME_JSON, encoding="utf-8")
    return ConfigManager(toml_path, json_path), json_path


class _StubCopTransport:
    """A genuinely independent Cop-side declaration, built the same way her
    real `_on_step0_received` builds one -- byte-identical `game.json`
    (same fixture content, different file/path) so `config_sha256` and
    `scent_model_sha256` legitimately agree, exactly the real-match
    precondition."""

    def __init__(self, shared_config_path, group_name="Cop-Team", tamper: str | None = None):
        self._shared_config_path = shared_config_path
        self._group_name = group_name
        self._tamper = tamper

    def call(self, tool_name, payload):
        assert tool_name == "receive_step0"
        from thief_peer.interop.cop_wire import current_git_commit_hash, hash_config_file

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
        if self._tamper == "config":
            declaration = {**declaration, "config_sha256": "0" * 64}
        if self._tamper == "scent":
            declaration = {**declaration, "scent_model_sha256": "0" * 64}
        signature = sign_cop_declaration(declaration)
        if self._tamper == "signature":
            signature = "0" * 64
        return {"declaration": declaration, "signature": signature, "repos": {"cop": "x", "thief": "y"}}


def test_cop_step0_handshake_succeeds_with_a_byte_identical_shared_config(tmp_path):
    config, json_path = _config_and_path(tmp_path)
    transport = _StubCopTransport(json_path)

    result = cop_step0_handshake(transport, config, "Thief-Team", 1, str(json_path), {"cop": "y", "thief": "x"})

    assert result["declaration"]["group_name"] == "Cop-Team"


def test_cop_step0_handshake_rejects_a_config_mismatch(tmp_path):
    config, json_path = _config_and_path(tmp_path)
    transport = _StubCopTransport(json_path, tamper="config")

    with pytest.raises(ConfigError, match="config_sha256"):
        cop_step0_handshake(transport, config, "Thief-Team", 1, str(json_path), {})


def test_cop_step0_handshake_rejects_a_scent_model_mismatch(tmp_path):
    config, json_path = _config_and_path(tmp_path)
    transport = _StubCopTransport(json_path, tamper="scent")

    with pytest.raises(ConfigError, match="scent_model_sha256"):
        cop_step0_handshake(transport, config, "Thief-Team", 1, str(json_path), {})


def test_cop_step0_handshake_rejects_a_tampered_signature(tmp_path):
    config, json_path = _config_and_path(tmp_path)
    transport = _StubCopTransport(json_path, tamper="signature")

    with pytest.raises(ConfigError, match="signature"):
        cop_step0_handshake(transport, config, "Thief-Team", 1, str(json_path), {})
