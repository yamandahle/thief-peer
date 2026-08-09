"""peer/sealing.py tests (PRD_6 §2.1, §2.5, §3, §5). github_commit_hash is
read from git HEAD, never hand-entered -- a stale hand-entered value could
silently drift from what's actually running (PRD_6 §4)."""

import subprocess

import pytest

from thief_peer.domain.crypto import CommitReveal
from thief_peer.exceptions import ConfigError
from thief_peer.peer.sealing import (
    REQUIRED_TERMS,
    current_git_commit_hash,
    sealed_spec_record,
    sealed_step_record,
    validate_required_terms,
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


def _complete_config(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text("[network]\nmy_port = 8802\n", encoding="utf-8")
    json_path = tmp_path / "game.json"
    json_path.write_text(_GAME_JSON, encoding="utf-8")
    return ConfigManager(toml_path, json_path)


def test_validate_required_terms_passes_with_a_complete_config(tmp_path):
    validate_required_terms(_complete_config(tmp_path))  # must not raise


def test_validate_required_terms_raises_config_error_on_a_missing_term(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text("[network]\nmy_port = 8802\n", encoding="utf-8")
    json_path = tmp_path / "game.json"
    json_path.write_text('{"board_and_agents": {"grid_size": 7}}', encoding="utf-8")
    config = ConfigManager(toml_path, json_path)

    with pytest.raises(ConfigError):
        validate_required_terms(config)


def test_required_terms_is_non_empty_and_covers_the_negotiation_vocabulary():
    assert len(REQUIRED_TERMS) > 0
    assert "board_and_agents.grid_size" in REQUIRED_TERMS


def test_sealed_step_record_has_the_seven_field_envelope_and_a_verifiable_commit():
    # 7 fields, matching the Cop repo's own CommitEnvelope shape (state,
    # move, intent, nonce, hint_text, step, role) -- adopted as this team's
    # own intra-pair standard, see peer/sealing.py's docstring.
    record = sealed_step_record(
        state="s1", move="N", intent="truth", hint_text="cold", step=1, role="thief"
    )

    assert set(record["payload"]) == {
        "state",
        "move",
        "intent",
        "nonce",
        "hint_text",
        "step",
        "role",
    }
    content = {k: v for k, v in record["payload"].items() if k != "nonce"}
    assert CommitReveal.verify(content, record["payload"]["nonce"], record["commit"])


def test_sealed_step_record_carries_the_given_values():
    record = sealed_step_record(
        state="s7", move="E", intent="lie", hint_text="warm", step=7, role="thief"
    )
    assert record["payload"]["state"] == "s7"
    assert record["payload"]["move"] == "E"
    assert record["payload"]["intent"] == "lie"
    assert record["payload"]["hint_text"] == "warm"
    assert record["payload"]["step"] == 7
    assert record["payload"]["role"] == "thief"


def test_sealed_spec_record_has_the_step0_fields_and_a_verifiable_commit():
    record = sealed_spec_record(group_name="My-Team")

    payload = record["payload"]
    assert set(payload) == {"spec", "code_version", "github_commit_hash", "group_name", "nonce"}
    assert payload["group_name"] == "My-Team"
    assert isinstance(payload["spec"], dict)

    content = {k: v for k, v in payload.items() if k != "nonce"}
    assert CommitReveal.verify(content, payload["nonce"], record["commit"])


def test_sealed_spec_record_github_commit_hash_matches_real_git_head():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    real_head = result.stdout.strip()

    record = sealed_spec_record(group_name="My-Team")

    assert record["payload"]["github_commit_hash"] == real_head


def test_current_git_commit_hash_is_a_40_character_hex_sha():
    sha = current_git_commit_hash()
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)
