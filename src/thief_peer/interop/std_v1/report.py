"""Builds the Section-12 `result_<game_id>.json` shape -- distinct from
Section 11's canonical consensus object (`audit.py::build_consensus_object`),
which is only the hashed subset. Everything here is [REPORT]: required in
our own file, never compared against the peer's, and a value the peer
never declared in its own negotiation offers is left empty rather than
guessed (Section 3's own rule).
"""

from __future__ import annotations

from datetime import UTC, datetime

_HEX_CHARS = set("0123456789abcdefABCDEF")


def valid_commit(value) -> str:
    """Section 3: "A value that is not exactly 40 hex characters is
    treated as absent." -- applied identically to our own declared commit
    and the peer's."""
    if isinstance(value, str) and len(value) == 40 and all(c in _HEX_CHARS for c in value):
        return value
    return ""


def group_details(identity: dict) -> dict:
    return {
        "group_id": identity.get("group_id", ""),
        "members": list(identity.get("members", [])),
        "repos": dict(identity.get("repos", {})),
        "mcp_servers": dict(identity.get("mcp_servers", {})),
        "llm_model": identity.get("llm_model", ""),
        "hardware_spec": identity.get("spec", {}),
    }


def final_result(
    rows: list[dict],
    my_group_id: str,
    their_group_id: str,
    games_played_including_this: int = 0,
    their_games_played_including_this: int | None = None,
) -> dict:
    """Section 6's cumulative series aggregate, including the +2 tie
    bonus -- applied once to each side, and only when the raw cumulative
    totals (before the bonus) are equal, regardless of which per-row
    outcomes produced them.

    `games_played_including_this`/`diversity_reward_applied` aren't part of
    the book's own canonical `final_result` schema (same conclusion
    `docs/TodoCloseGaps.md` reached for the native path's own
    `report/series_result.py::merge_sub_game_into_series`) -- carried
    through here for the same reason: harmless bonus fields, computed
    honestly from data already available rather than hardcoded. Both are
    now per-group objects (reconciled live against yanell11 -- rule-38's
    own count is inherently per-team, since each side tracks its own
    separate counter): our own value from `LeagueCounter` (via
    `interop/std_v1_opponent.py`), theirs from whatever they actually
    declared on the wire (`counted_games_played`, spec Section 3) --
    `None` when they never declared one, not a guessed 0, since an absent
    peer declaration is a real fact worth keeping distinct from an
    explicitly-declared zero. No diversity-bonus logic exists in this
    repo, so `diversity_reward_applied` is always `False` for both
    sides."""
    total = {my_group_id: 0, their_group_id: 0}
    won = {my_group_id: 0, their_group_id: 0}
    ties = 0
    for row in rows:
        total[my_group_id] += row["score"].get(my_group_id, 0)
        total[their_group_id] += row["score"].get(their_group_id, 0)
        if row["winner_group"] is None:
            ties += 1
        else:
            won[row["winner_group"]] += 1

    series_tie = total[my_group_id] == total[their_group_id]
    if series_tie:
        total = {group: score + 2 for group, score in total.items()}
        winner_group = None
    else:
        winner_group = my_group_id if total[my_group_id] > total[their_group_id] else their_group_id

    return {
        "total_score": total,
        "sub_games_won": won,
        "ties": ties,
        "winner_group": winner_group,
        "series_tie": series_tie,
        "tokens_total_series": {my_group_id: 0, their_group_id: 0},
        "games_played_including_this": {
            my_group_id: games_played_including_this,
            their_group_id: their_games_played_including_this,
        },
        "diversity_reward_applied": {my_group_id: False, their_group_id: False},
    }


def build_result_report(
    game_id: str,
    game_uid: str,
    my_group_id: str,
    their_group_id: str,
    my_identity: dict,
    their_identity: dict,
    rows: list[dict],
    sub_game_meta: list[dict],
    mutual_agreement: dict,
    game_started_at: str,
    game_ended_at: str,
    games_played_including_this: int = 0,
    their_games_played_including_this: int | None = None,
) -> dict:
    """`sub_game_meta[i]` supplies the per-row fields Section 11's own
    canonical row doesn't carry: `their_github_commit`, `steps`,
    `started_at`, `ended_at`, and this sub-game's own `audit` outcome
    (`log_verified`/`tampered`/`result_agreed`)."""
    # One log file for the whole series (interop/std_v1_opponent.py writes
    # it under this exact name, mirroring report/artifact_helpers.py's own
    # `log_{game_uid}.json` convention) -- every sub-game's records live in
    # it together, tagged by `sub_game_number` (replay_log.py::build_records),
    # so every row references the same file rather than a per-sub-game one.
    # `log_files` is keyed per-group (reconciled live against yanell11),
    # not a plain list -- both sides currently point at this same one file
    # since neither side's own log is split per sub-game, but the shape
    # leaves room for a peer whose own log naming differs per side.
    log_filename = f"log_{game_uid}.json"
    sub_games = []
    for row, meta in zip(rows, sub_game_meta, strict=True):
        sub_games.append({
            **row,
            "tie": row["winner_group"] is None,
            "github_commit": {
                my_group_id: valid_commit(my_identity.get("github_commit")),
                their_group_id: valid_commit(meta["their_github_commit"]),
            },
            "tokens": {my_group_id: 0, their_group_id: 0},
            "audit": meta["audit"],
            "log_files": {my_group_id: log_filename, their_group_id: log_filename},
            "steps": meta["steps"],
            "started_at": meta["started_at"],
            "ended_at": meta["ended_at"],
        })

    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "report_type": "std_v1_result",
        "schema_version": "1.0",
        "groups": [my_group_id, their_group_id],
        "sub_games": sub_games,
        # `declaration`/`config`/`log`/`result` name the four artifacts this
        # side actually writes for the whole series (interop/std_v1_opponent.
        # py::write_std_v1_declaration/write_std_v1_config/write_std_v1_log/
        # write_std_v1_result) -- the canonical schema's own "static
        # metadata isn't repeated here" note is deliberately overridden for
        # `github`: the 4 repo URLs (both teams' Cop and Thief repos) are
        # embedded directly rather than left for a reader to reconstruct
        # from the pre-game declaration alone.
        "links": {
            "declaration": f"declaration_{game_id}.json",
            "config": f"config_{game_uid}.json",
            "log": log_filename,
            "result": f"result_{game_id}.json",
            "github": {
                my_group_id: my_identity.get("repos", {}),
                their_group_id: their_identity.get("repos", {}),
            },
        },
        "group_details": {
            my_group_id: group_details(my_identity),
            their_group_id: group_details(their_identity),
        },
        "timezone": "UTC",
        "game_started_at": game_started_at,
        "game_ended_at": game_ended_at,
        "mutual_agreement": mutual_agreement,
        "final_result": final_result(
            rows, my_group_id, their_group_id,
            games_played_including_this, their_games_played_including_this,
        ),
    }


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
