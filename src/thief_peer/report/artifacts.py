"""Pure builders for the four Table-20 JSON artifacts (book Ch.9 / Appendix ו).
Shapes mirror the book's own reference implementation exactly
(github.com/rmisegal/Game-P2P-Cop-Chase, docs/sample-run/*.json) -- field
names, nesting and envelope keys (_schema, schema_version, links, ...), not
just the game data itself."""

from thief_peer.report.artifact_helpers import (
    canonical_sha256,
    config_filename,
    consensus_signature,
    group_block,
    links_block,
    tokens_series,
)
from thief_peer.report.artifact_schemas import DECLARATION_TYPE, REPORT_TYPE, SCHEMA_VERSION

_DECLARATION_SCHEMA = (
    "Static declaration for the whole game (the full series of sub-games) "
    "between two groups: identity, members, repos, MCP server URLs, "
    "hardware, LLM model, the agreed max-tokens-per-game cap, and the game "
    "start/end times. Both groups sign and lock it cryptographically before "
    "play (book ch.5 Step-0)."
)

_CONFIG_SCHEMA = (
    "Agreed game configuration for one sub-game. Values come from the "
    "master parameter table (Appendix ו); both peers hold a byte-identical "
    "copy, locked cryptographically via config_sha256."
)
_CONFIG_NOTE = (
    "Shared, agreed game terms. Both peers must hold a byte-identical copy; "
    "the pre-game signature exchange refuses to play on any mismatch."
)

_LOG_SCHEMA = (
    "Per-sub-game match log for cryptographic audit in the Replay Simulator "
    "(book ch.7). Each step is committed as SHA-256(state || move || intent "
    "|| nonce) and later revealed; nonces are revealed only at the final "
    "audit (book ch.5 commit-reveal)."
)

_RESULT_SCHEMA = (
    "Final results report for the whole game (all sub-games): each group's "
    "score per sub-game and the cumulative outcome, for the lecturer to "
    "weigh into the league score. Both groups must agree on it and each "
    "sends its own copy (book ch.9)."
)


def build_declaration(
    game_id: str,
    game_uid: str,
    *,
    timezone: str,
    game_started_at: str,
    game_ended_at: str,
    num_sub_games: int,
    max_tokens_per_game: int,
    own: dict,
    opponent: dict,
) -> dict:
    return {
        "_schema": _DECLARATION_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "declaration_type": DECLARATION_TYPE,
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links_block(game_id),
        "timezone": timezone,
        "game_started_at": game_started_at,
        "game_ended_at": game_ended_at,
        "num_sub_games": num_sub_games,
        "max_tokens_per_game": max_tokens_per_game,
        "groups": {"group_1": group_block(own), "group_2": group_block(opponent)},
    }


def build_config(
    shared_terms: dict,
    game_id: str,
    game_uid: str,
    sub_game_number: int,
    agreed_between: list[str],
) -> dict:
    return {
        "_schema": _CONFIG_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "_note": _CONFIG_NOTE,
        "agreed_between": list(agreed_between),
        **shared_terms,
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "links": links_block(game_id),
        "config_name": config_filename(game_id, sub_game_number),
        "config_sha256": canonical_sha256(shared_terms),
    }


def build_log(summary: dict, game_id: str, game_uid: str) -> dict:
    records = summary["records"]
    log_summary = {key: value for key, value in summary.items() if key != "records"}
    return {
        "_schema": _LOG_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links_block(game_id),
        "summary": log_summary,
        "records": records,
        "mutual_agreement": {
            "opponent_group_id": summary["opponent_group_id"],
            "sha256": consensus_signature(records),
            "confirmed": bool(summary["audit"]["passed"]),
        },
    }


def build_result(
    game_id: str,
    game_uid: str,
    timezone: str,
    group_ids: list[str],
    sub_games: list[dict],
    aggregate: dict,
    mutual_sha256: str,
) -> dict:
    final_result = {**aggregate, "tokens_total_series": tokens_series(sub_games, group_ids)}
    return {
        "_schema": _RESULT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links_block(game_id),
        "timezone": timezone,
        "groups": list(group_ids),
        "num_sub_games": len(sub_games),
        "sub_games": sub_games,
        "final_result": final_result,
        "mutual_agreement": {
            "sha256": mutual_sha256,
            "confirmed": all(sg.get("audit", {}).get("log_verified", False) for sg in sub_games),
        },
    }
