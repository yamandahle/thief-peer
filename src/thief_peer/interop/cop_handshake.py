"""Step-0 exchange with a real Cop peer (ch.5.5) -- the *only* live
negotiation point her side actually has. Unlike a native Thief opponent
(`peer/handshake.py`'s `negotiate` + `receive_control`), her repo has no
live tool for the shared `game.json` terms at all: config agreement is a
byte-identical shared file, checked here the same way her own
`_verify_peer_step0` checks it (`config_sha256`) -- rather than our own
Commit-Reveal `negotiate()` exchange, which she has no tool to answer.
"""

import secrets

from thief_peer.domain.scent_lock import scent_lock_hash
from thief_peer.exceptions import ConfigError
from thief_peer.interop.cop_wire import (
    build_cop_declaration,
    build_cop_hardware,
    current_git_commit_hash,
    hash_config_file,
    sign_cop_declaration,
)
from thief_peer.shared import sysinfo
from thief_peer.shared.config import ConfigManager


def _my_scent_lock_hash(config: ConfigManager) -> str:
    return scent_lock_hash(
        config.require("pheromones.pheromone_center_intensity"),
        config.require("pheromones.pheromone_decay"),
        config.require("pheromones.pheromone_grid_size"),
    )


def build_own_declaration(
    config: ConfigManager, group_name: str, sub_game_number: int, shared_config_path: str
) -> dict:
    hardware = build_cop_hardware(sysinfo.collect_spec(), config.get("llm.model", "template"))
    return build_cop_declaration(
        hardware=hardware,
        code_commit_hash=current_git_commit_hash(),
        group_name=group_name,
        sub_game_number=sub_game_number,
        config_sha256=hash_config_file(shared_config_path),
        scent_model_sha256=_my_scent_lock_hash(config),
    )


def verify_their_declaration(declaration: dict, signature: str, my_declaration: dict) -> None:
    """Mirrors her own `_verify_peer_step0`: signature integrity, then
    `config_sha256` (rule 11), then `scent_model_sha256` (ch.4.5, rule 23) --
    each a real, independently-checkable guarantee even though the deeper
    per-turn commit envelope remains incompatible (see this package's own
    `__init__.py` docstring)."""
    if not secrets.compare_digest(sign_cop_declaration(declaration), signature):
        raise ConfigError("Cop peer's Step-0 signature does not match their own declaration")
    if not secrets.compare_digest(declaration["config_sha256"], my_declaration["config_sha256"]):
        raise ConfigError(
            "Cop peer's config_sha256 does not match ours (rule 11) -- the shared "
            "game.json files are not byte-identical"
        )
    if not secrets.compare_digest(
        declaration["scent_model_sha256"], my_declaration["scent_model_sha256"]
    ):
        raise ConfigError(
            "Cop peer's scent_model_sha256 does not match ours (ch.4.5, rule 23) -- "
            "the pheromone formula implementations have diverged"
        )


def cop_step0_handshake(
    transport,
    config: ConfigManager,
    group_name: str,
    sub_game_number: int,
    shared_config_path: str,
    repos: dict,
) -> dict:
    my_declaration = build_own_declaration(config, group_name, sub_game_number, shared_config_path)
    my_signature = sign_cop_declaration(my_declaration)

    response = transport.call(
        "receive_step0",
        {"declaration": my_declaration, "signature": my_signature, "repos": repos},
    )
    verify_their_declaration(response["declaration"], response["signature"], my_declaration)
    return response
