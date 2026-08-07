"""Helpers shared by report/artifacts.py (PRD_7 §2.6, §3). canonical_sha256
reuses domain/crypto.py's canonical_json (Stage 6, DRY) -- never a second,
independently-drifting serialization implementation."""

import hashlib

from thief_peer.domain.crypto import canonical_json
from thief_peer.domain.game_ids import derive_game_uid


def canonical_sha256(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def artifact_filenames(game_id: str, sub_game_number: int) -> dict[str, str]:
    """Matches book Appendix ו's naming exactly: declaration/result are once
    per match; config/log are once per sub-game."""
    game_uid = derive_game_uid(game_id, sub_game_number)
    return {
        "declaration": f"declaration_{game_id}.json",
        "config": f"config_{game_uid}.json",
        "log": f"log_{game_uid}.json",
        "result": f"result_{game_id}.json",
    }
