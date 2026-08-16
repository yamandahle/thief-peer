"""Series-level result-file accumulation. `result_<game_id>.json` is the
one artifact that spans the whole match series (not just one sub-game),
so writing it isn't a pure function like `artifacts.py`'s builders -- it
must read whatever's already on disk, merge this sub-game in, and
recompute `final_result` from the complete accumulated array. This
mirrors the real Cop peer's own reference implementation exactly: no new
state file, `sub_games` state lives entirely inside the result artifact
itself, keyed by `sub_game_number`, replaced (not appended) on a re-run.

The result artifact's own `game_uid` (this module generates it once via
`uuid.uuid4()` and persists it by reading it back on every later call) is
a distinct, series-stable identifier -- NOT the same concept as
`domain/game_ids.py::derive_game_uid`'s per-sub-game `<game_id>_g<NN>`
value used for the `config_`/`log_` filenames. The real Cop peer's own
live output confirms this naming split.
"""

import json
import uuid
from pathlib import Path

from thief_peer.domain.scoring import aggregate_series
from thief_peer.report.artifact_helpers import artifact_filenames, canonical_sha256
from thief_peer.report.artifact_schemas import SCHEMA_VERSION
from thief_peer.report.artifacts import build_result


def merge_sub_game_into_series(
    results_dir: str | Path,
    game_id: str,
    group_a: str,
    group_b: str,
    num_sub_games: int,
    this_sub_game: dict,
    games_played_including_this: int,
    league_params: dict | None = None,
) -> dict:
    path = Path(results_dir) / f"result_{game_id}.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    # A file left over from before this schema existed (or a future,
    # incompatible one) has no reliable `sub_games`/`game_uid` to build on
    # -- start this series fresh rather than crashing on a stale layout.
    if existing is not None and existing.get("schema_version") != SCHEMA_VERSION:
        existing = None
    game_uid = existing["game_uid"] if existing else str(uuid.uuid4())

    sub_games = [
        sg
        for sg in (existing["sub_games"] if existing else [])
        if sg["sub_game_number"] != this_sub_game["sub_game_number"]
    ]
    sub_games.append(this_sub_game)
    sub_games.sort(key=lambda sg: sg["sub_game_number"])

    final_result = aggregate_series(sub_games, group_a, group_b)
    # Bonus fields seen in the real Cop peer's live output, not part of the
    # book's own reference schema -- included for interop-friendliness,
    # computed honestly from data we already have rather than hardcoded.
    final_result["games_played_including_this"] = games_played_including_this
    final_result["diversity_reward_applied"] = False
    # docs/TodoCloseGaps.md #4: lecturer/league-management fields
    # (diversity_reward, min_games_to_pass, max_games_per_team,
    # token_budget_per_series) -- confirmed not part of the book's own
    # canonical schema, no local behavior reads them, but carried through
    # verbatim for completeness. `diversity_reward` (a raw config scalar)
    # is deliberately distinct from `diversity_reward_applied` above (a
    # boolean, always False here since no diversity-bonus logic exists).
    final_result.update(league_params or {})

    filenames = artifact_filenames(game_id, this_sub_game["sub_game_number"])
    links = {
        "declaration": f"declaration_{game_id}.json",
        "config": filenames["config"],
        "log": filenames["log"],
        "result": f"result_{game_id}.json",
    }

    result = build_result(
        game_id=game_id,
        game_uid=game_uid,
        groups=[group_a, group_b],
        num_sub_games=num_sub_games,
        sub_games=sub_games,
        final_result=final_result,
        mutual_agreement=None,
        links=links,
    )
    payload_for_hash = {k: v for k, v in result.items() if k != "mutual_agreement"}
    result["mutual_agreement"] = {
        "sha256": canonical_sha256(payload_for_hash),
        "confirmed": all(sg["audit"]["log_verified"] for sg in sub_games),
    }
    return result
