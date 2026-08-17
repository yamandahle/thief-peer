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


def final_result(rows: list[dict], my_group_id: str, their_group_id: str) -> dict:
    """Section 6's cumulative series aggregate, including the +2 tie
    bonus -- applied once to each side, and only when the raw cumulative
    totals (before the bonus) are equal, regardless of which per-row
    outcomes produced them."""
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
) -> dict:
    """`sub_game_meta[i]` supplies the per-row fields Section 11's own
    canonical row doesn't carry: `their_github_commit`, `steps`,
    `started_at`, `ended_at`, and this sub-game's own `audit` outcome
    (`log_verified`/`tampered`/`result_agreed`)."""
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
            "log_files": [],
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
        "links": {
            "github": {
                my_group_id: my_identity.get("repos", {}),
                their_group_id: their_identity.get("repos", {}),
            }
        },
        "group_details": {
            my_group_id: group_details(my_identity),
            their_group_id: group_details(their_identity),
        },
        "timezone": "UTC",
        "game_started_at": game_started_at,
        "game_ended_at": game_ended_at,
        "mutual_agreement": mutual_agreement,
        "final_result": final_result(rows, my_group_id, their_group_id),
    }


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
