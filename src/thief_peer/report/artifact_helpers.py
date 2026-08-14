"""Shared helpers for the four Table-20 JSON artifacts (book Ch.9 / PLAN.md §5)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from thief_peer.domain.crypto import canonical_json

_CONFIG_ARTIFACT_KEYS = frozenset(
    {
        "_schema",
        "_note",
        "game_id",
        "game_uid",
        "sub_game_number",
        "links",
        "config_name",
        "config_sha256",
        "agreed_between",
    }
)


def consensus_signature(data) -> str:
    """SHA-256 over canonical JSON -- reuses domain/crypto.py's canonical_json
    (Stage 6, DRY) so this never drifts from the Commit-Reveal hash's own
    serialization."""
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def canonical_sha256(payload: dict) -> str:
    return consensus_signature(payload)


def declaration_filename(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def config_filename(game_id: str, sub_game_number: int) -> str:
    return f"config_{game_id}_g{sub_game_number:02d}.json"


def log_filename(game_id: str, sub_game_number: int) -> str:
    return f"log_{game_id}_g{sub_game_number:02d}.json"


def result_filename(game_id: str) -> str:
    return f"result_{game_id}.json"


def artifact_filenames(game_id: str, sub_game_number: int) -> dict[str, str]:
    return {
        "declaration": declaration_filename(game_id),
        "config": config_filename(game_id, sub_game_number),
        "log": log_filename(game_id, sub_game_number),
        "result": result_filename(game_id),
    }


def links_block(game_id: str) -> dict:
    """The book's own Table-20 reference block (Appendix ו), embedded in
    every artifact. Logical roles, not fixed filenames -- config/log use the
    literal '<NN>' placeholder since those two are per-sub-game; declaration/
    result are once per whole game and so resolve to a real filename."""
    return {
        "_remark": (
            "These are logical roles, not fixed filenames. Each file name is "
            "derived from game_id so files from different games are never "
            "mixed. Match-level files (declaration, result) are named "
            "<role>_<game_id>.json; per-sub-game files (config, log) are "
            "named <role>_<game_id>_g<NN>.json where <NN> is the "
            "sub_game_number."
        ),
        "declaration": declaration_filename(game_id),
        "config": f"config_{game_id}_g<NN>.json",
        "log": f"log_{game_id}_g<NN>.json",
        "result": result_filename(game_id),
    }


def load_shared_config_terms(path: str | Path) -> dict:
    """Negotiated game.json body — shared terms only, no artifact envelope keys."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if key not in _CONFIG_ARTIFACT_KEYS}


def ended_at(started_at: str, duration_seconds: float) -> str:
    try:
        start = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return started_at
    return (start + timedelta(seconds=duration_seconds)).isoformat()


def hardware_spec_block(spec: dict | None) -> dict:
    spec = spec or {}
    return {
        "cpu_type": spec.get("cpu_type", spec.get("cpu")),
        "cpu_freq_mhz": spec.get("cpu_freq_mhz"),
        "cpu_cores": spec.get("cpu_cores"),
        "ram_gb": spec.get("ram_gb"),
        "gpu_model": spec.get("gpu_model", spec.get("gpu")),
        "vram_gb": spec.get("vram_gb", spec.get("gpu_vram_gb")),
    }


def group_block(identity: dict) -> dict:
    """One team's static declaration block (book ch.9 / Appendix ו).
    `team_code` (rule 45 [MUST]) is `None` whenever the caller didn't
    supply one -- a dev/warm-up run, or an opponent whose own code we
    were never told -- never fabricated."""
    block = {
        "group_id": identity["group_id"],
        "group_name": identity["group_name"],
        "team_code": identity.get("team_code"),
        "members": list(identity.get("members") or []),
        "repos": dict(identity.get("repos") or {}),
        "mcp_servers": dict(identity.get("mcp_servers") or {}),
        "llm_model": identity.get("llm_model") or "none",
        "hardware_spec": hardware_spec_block(identity.get("hardware_spec")),
    }
    block["signature"] = consensus_signature(block)
    return block


def tokens_series(sub_games: list[dict], group_ids: list[str]) -> dict:
    return {group_id: sum(sg.get("tokens", {}).get(group_id, 0) for sg in sub_games) for group_id in group_ids}


def merge_sub_games(previous: list[dict], new_entry: dict) -> list[dict]:
    """Book ch.9.4: result_<game_id>.json is the summary for the WHOLE
    series (up to 6 sub-games, PARAMETERS.md Table 18), not a single
    sub-game -- each sub-game is a separate `PeerRuntime` process, so the
    only way to accumulate across them is read-merge-write against the
    file the previous sub-game(s) already left on disk. Replace-or-append
    by `sub_game_number`, not a blind append: a retried/re-run sub-game
    must overwrite its own old entry, never duplicate it."""
    merged = [sg for sg in previous if sg.get("sub_game_number") != new_entry["sub_game_number"]]
    merged.append(new_entry)
    merged.sort(key=lambda sg: sg["sub_game_number"])
    return merged


def aggregate_series(sub_games: list[dict], group_name: str, opponent_group_name: str) -> dict:
    """Recompute total_score/sub_games_won/series winner from every
    sub-game recorded so far. `sub_games_won` reuses each sub-game's own
    already-decided `winner_group` (which correctly encodes
    technical-loss fault, not just a score comparison), so a 0-0
    technical-loss sub-game still counts as a real win for whichever side
    wasn't at fault.

    The series `winner_group`/`series_tie` themselves are decided by
    accumulated POINTS first (book p.71's own Tie Rule: "if the
    cumulative SCORE of all sub-games ends in a tie -- i.e. the sum of
    points is equal"), falling back to the sub-games-won count only when
    points are exactly equal too. A lone technical-loss sub-game (0-0,
    tied on points by definition) still needs *some* winner -- that's
    what the sub-games-won fallback is for; a genuine points tie with an
    even sub-games-won split is the only case that's a real series tie."""
    total_score = {group_name: 0, opponent_group_name: 0}
    sub_games_won = {group_name: 0, opponent_group_name: 0}
    ties = 0
    for sub_game in sub_games:
        score = sub_game.get("score", {})
        total_score[group_name] += int(score.get(group_name, 0))
        total_score[opponent_group_name] += int(score.get(opponent_group_name, 0))
        sub_game_winner = sub_game.get("winner_group")
        if sub_game_winner == group_name:
            sub_games_won[group_name] += 1
        elif sub_game_winner == opponent_group_name:
            sub_games_won[opponent_group_name] += 1
        else:
            ties += 1

    if total_score[group_name] != total_score[opponent_group_name]:
        winner_group = group_name if total_score[group_name] > total_score[opponent_group_name] else opponent_group_name
        series_tie = False
    elif sub_games_won[group_name] != sub_games_won[opponent_group_name]:
        winner_group = group_name if sub_games_won[group_name] > sub_games_won[opponent_group_name] else opponent_group_name
        series_tie = False
    else:
        winner_group, series_tie = None, True

    return {
        "total_score": total_score,
        "sub_games_won": sub_games_won,
        "ties": ties,
        "winner_group": winner_group,
        "series_tie": series_tie,
    }
