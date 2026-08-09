"""peer/handshake.py tests (PRD_6 §2.5, §3). Exercised against a stub
transport that behaves like a real, independently-configured opponent peer
-- proving the negotiation-then-Step-0 sequence genuinely works two-sided,
not just that each half works in isolation. A real MCP-backed transport is
wired in once `PeerRuntime` exists (later stage)."""

import pytest

from thief_peer.domain.crypto import hash_config_file
from thief_peer.domain.negotiation import Negotiation, canonical_terms
from thief_peer.exceptions import ConfigError
from thief_peer.peer.handshake import run_handshake
from thief_peer.peer.sealing import sealed_spec_record
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


def _config(tmp_path, name="game", grid_size=7):
    toml_path = tmp_path / f"{name}.toml"
    toml_path.write_text("[network]\nmy_port = 8802\n", encoding="utf-8")
    json_path = tmp_path / f"{name}.json"
    json_path.write_text(_GAME_JSON.replace('"grid_size": 7', f'"grid_size": {grid_size}'), encoding="utf-8")
    return ConfigManager(toml_path, json_path)


class _StubPeerTransport:
    """Stands in for a real, independently-configured opponent peer: it
    has its own config and responds to negotiate/receive_control with its
    own genuinely-computed signatures, exactly as a real Cop process would."""

    def __init__(self, their_config: ConfigManager, their_group_name: str, their_json_path=None):
        self._their_config = their_config
        self._their_group_name = their_group_name
        self._their_json_path = their_json_path

    def call(self, tool_name: str, payload: dict) -> dict:
        if tool_name == "negotiate":
            config_sha256 = (
                hash_config_file(self._their_json_path) if self._their_json_path else None
            )
            return Negotiation.signed(
                canonical_terms(self._their_config), config_sha256=config_sha256
            )
        if tool_name == "receive_control" and payload.get("type") == "step0":
            return {"record": sealed_spec_record(self._their_group_name)}
        raise ValueError(f"unexpected tool call: {tool_name}")


def test_run_handshake_returns_the_opponents_verified_step0_record(tmp_path):
    my_config = _config(tmp_path, "mine")
    their_config = _config(tmp_path, "theirs")
    transport = _StubPeerTransport(their_config, their_group_name="Cop-Team")

    their_record = run_handshake(my_config, transport, group_name="Thief-Team")

    assert their_record["payload"]["group_name"] == "Cop-Team"


def test_run_handshake_raises_on_a_terms_mismatch_before_any_step0_exchange(tmp_path):
    my_config = _config(tmp_path, "mine", grid_size=7)
    their_config = _config(tmp_path, "theirs", grid_size=9)  # deliberately different
    transport = _StubPeerTransport(their_config, their_group_name="Cop-Team")

    with pytest.raises(ConfigError, match="grid_size"):
        run_handshake(my_config, transport, group_name="Thief-Team")


class _ScentDriftPeerTransport(_StubPeerTransport):
    """Same negotiated numbers as a real peer, but a tampered scent-lock
    hash -- simulates an opponent whose ScentField implementation has
    silently drifted (ch.4.5, rule 23) despite reporting identical config
    values, which `_StubPeerTransport` alone can't exercise."""

    def call(self, tool_name: str, payload: dict) -> dict:
        result = super().call(tool_name, payload)
        if tool_name == "negotiate":
            result = {**result, "scent_lock_hash": "0" * 64}
        return result


def test_run_handshake_raises_on_a_scent_lock_drift_even_with_matching_terms(tmp_path):
    my_config = _config(tmp_path, "mine")
    their_config = _config(tmp_path, "theirs")
    transport = _ScentDriftPeerTransport(their_config, their_group_name="Cop-Team")

    with pytest.raises(ConfigError, match="scent-lock"):
        run_handshake(my_config, transport, group_name="Thief-Team")


def test_run_handshake_accepts_a_byte_identical_shared_config_file(tmp_path):
    # Same file content, deliberately two separate files on disk -- exactly
    # the real scenario (each side has its own copy) rather than the same
    # path, which would prove nothing.
    my_config = _config(tmp_path, "mine")
    their_config = _config(tmp_path, "theirs")  # _GAME_JSON, unmodified -- byte-identical
    transport = _StubPeerTransport(
        their_config, their_group_name="Cop-Team", their_json_path=tmp_path / "theirs.json"
    )

    run_handshake(
        my_config, transport, group_name="Thief-Team", shared_config_path=tmp_path / "mine.json"
    )  # must not raise


def test_run_handshake_rejects_a_non_byte_identical_shared_config_file(tmp_path):
    # Deliberately different formatting (trailing whitespace) but the exact
    # same negotiated *values* -- the term-by-term check alone would pass
    # this; rule 11 requires catching it anyway.
    my_config = _config(tmp_path, "mine")
    _config(tmp_path, "theirs")
    their_json_path = tmp_path / "theirs.json"
    their_json_path.write_text(their_json_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    their_config = ConfigManager(tmp_path / "theirs.toml", their_json_path)
    transport = _StubPeerTransport(
        their_config, their_group_name="Cop-Team", their_json_path=their_json_path
    )

    with pytest.raises(ConfigError, match="byte-identical"):
        run_handshake(
            my_config,
            transport,
            group_name="Thief-Team",
            shared_config_path=tmp_path / "mine.json",
        )


def test_run_handshake_skips_the_file_check_when_shared_config_path_is_not_given(tmp_path):
    # Backward-compatible default: an isolated caller with no file path
    # handy must not be forced into rule 11's stricter check.
    my_config = _config(tmp_path, "mine")
    their_config = _config(tmp_path, "theirs")
    transport = _StubPeerTransport(
        their_config, their_group_name="Cop-Team", their_json_path=tmp_path / "theirs.json"
    )

    run_handshake(my_config, transport, group_name="Thief-Team")  # must not raise
