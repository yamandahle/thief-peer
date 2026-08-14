"""finalize_match (PRD_8 §2.5): end-of-match audit + Table-20 JSON report.

Rule 19 (book p.129, [FATAL]): any hash mismatch found during the audit
is "the iron law dictating score 0 for the forging team" -- not just a
`winner`/`tampered` flag written honestly into the report while the score
numbers carry on as if nothing happened. `winner` already correctly
flipped to the honest side on a failed audit; the score itself didn't.
Fixed below: whichever side's audit fails has its own score entry forced
to 0, independent of `result_word` -- the other side keeps whatever the
real board outcome (capture/survival) earned them. `end_reason ==
"technical_loss"` already scores 0-0 through the ordinary `_score_pair`
path (a separate, pre-existing mechanism); this only covers the case a
technical loss doesn't -- a match that looked clean while it was being
played, tampered log discovered only at the very end.

Book ch.9.4: `result_<game_id>.json` is "the summary and final result for
the WHOLE series" (up to 6 sub-games, PARAMETERS.md Table 18), and rule
32/9.3 only requires ONE automatic report per legal series, not one per
sub-game. This used to build `result_` fresh from just this one sub-game
and email it every single time. Fixed: every call now reads back whatever
`result_<game_id>.json` the previous sub-game(s) already left on disk
(each sub-game is a separate process, so this is the only way to
accumulate across them), merges this sub-game's own entry in
(`artifact_helpers.merge_sub_games`), recomputes the real series totals
over the full merged list (`artifact_helpers.aggregate_series`), and
persists that -- every call, unconditionally, since the running series
state has to be somewhere between processes. Only the Gatekeeper/email
dispatch is gated to `sub_game_number == num_sub_games`; every earlier
call returns without sending.
"""

from datetime import UTC, datetime
from pathlib import Path

from thief_peer.domain.crypto import audit_records
from thief_peer.domain.game_ids import derive_game_id, derive_game_uid
from thief_peer.domain.protocol import build_audit_payload
from thief_peer.report.artifact_helpers import (
    aggregate_series,
    consensus_signature,
    load_shared_config_terms,
    log_filename,
    merge_sub_games,
    result_filename,
    tokens_series,
)
from thief_peer.report.artifact_schemas import DEFAULT_TIMEZONE
from thief_peer.report.report_writer import LeagueCounter, load_previous_result, write_and_send
from thief_peer.shared import sysinfo

_SENDER = "thief"
_WINNER_IS_OPPONENT = {"technical_loss", "captured"}
_NATIVE_STYLE_AUDIT_PROTOCOLS = {"native"}


def _end_reason_to_result_word(end_reason: str) -> str:
    return {
        "survived": "survival",
        "max_moves_reached": "survival",
        "captured": "capture",
        "technical_loss": "technical_loss",
    }.get(end_reason, end_reason)


def _winner_role(winner_group: str, group_name: str) -> str:
    return "thief" if winner_group == group_name else "police"


def _score_pair(config, result_word: str, group_name: str, opponent_group_name: str) -> dict:
    if result_word == "capture":
        thief_pts = int(config.require("scoring.capture_thief"))
        cop_pts = int(config.require("scoring.capture_cop"))
    elif result_word == "survival":
        thief_pts = int(config.require("scoring.survival_thief"))
        cop_pts = int(config.require("scoring.survival_cop"))
    else:
        thief_pts = cop_pts = 0
    return {group_name: thief_pts, opponent_group_name: cop_pts}


def finalize_match(
    group_name: str,
    opponent_group_name: str,
    end_reason: str,
    records: list[dict],
    config,
    transport,
    gatekeeper,
    email_service,
    recipient: str,
    results_dir,
    sub_game_number: int,
    num_sub_games: int,
    repos: dict | None = None,
    is_counted: bool = True,
    opponent_protocol: str = "native",
    precomputed_self_audit: dict | None = None,
    precomputed_opponent_audit: dict | None = None,
    opponent_repos: dict | None = None,
    tokens_own: int = 0,
    tokens_opponent: int | None = None,
    game_started_at: str | None = None,
    game_ended_at: str | None = None,
    own_members: list | None = None,
    opponent_members: list | None = None,
    own_llm_model: str | None = None,
    opponent_llm_model: str | None = None,
    own_mcp_url: str | None = None,
    opponent_mcp_url: str | None = None,
    own_spec: dict | None = None,
    opponent_spec: dict | None = None,
    github_commit_own: str | None = None,
    github_commit_opponent: str | None = None,
    shared_config_path: str | None = None,
    own_team_code: str | None = None,
) -> dict:
    game_id = derive_game_id(*sorted([group_name, opponent_group_name]))
    game_uid = derive_game_uid(game_id, sub_game_number)
    result_claim = "technical_loss" if end_reason == "technical_loss" else "survival"
    ended = game_ended_at or datetime.now(UTC).isoformat()
    started = game_started_at or ended

    _not_evaluated = {"passed": False, "verified_steps": 0, "failed_steps": [], "evaluated": False}
    if precomputed_self_audit is not None and precomputed_opponent_audit is not None:
        self_audit = precomputed_self_audit
        opponent_audit = precomputed_opponent_audit
        audit_was_evaluated = end_reason != "technical_loss" and (
            bool(self_audit.get("evaluated")) or bool(opponent_audit.get("evaluated"))
        )
    elif end_reason == "technical_loss" or opponent_protocol not in _NATIVE_STYLE_AUDIT_PROTOCOLS:
        self_audit = _not_evaluated
        opponent_audit = _not_evaluated
        audit_was_evaluated = False
    else:
        audit_payload = build_audit_payload(_SENDER, result_claim, records)
        self_audit = transport.call("submit_audit", {"payload": audit_payload})
        their_records = transport.call("get_revealed_records", {"payload": {}})["records"]
        opponent_audit = audit_records(their_records)
        audit_was_evaluated = True

    log_audit = {
        "passed": bool(self_audit.get("passed")) and bool(opponent_audit.get("passed")),
        "verified_steps": int(self_audit.get("verified_steps", 0)),
        "failed_steps": list(self_audit.get("failed_steps") or []),
    }
    log_verified = log_audit["passed"] and audit_was_evaluated

    opponent_forged = bool(
        audit_was_evaluated and opponent_audit.get("evaluated", True) and not opponent_audit["passed"]
    )
    we_forged = bool(
        audit_was_evaluated and self_audit.get("evaluated", True) and not self_audit["passed"]
    )

    if opponent_forged:
        winner = group_name
    elif we_forged or end_reason in _WINNER_IS_OPPONENT:
        winner = opponent_group_name
    else:
        winner = group_name

    result_word = _end_reason_to_result_word(end_reason)
    tokens_opp = 0 if tokens_opponent is None else tokens_opponent
    tokens_map = {group_name: int(tokens_own), opponent_group_name: int(tokens_opp)}
    score_map = _score_pair(config, result_word, group_name, opponent_group_name)
    # Rule 19 [FATAL], "iron law": whichever side's data fails the audit
    # scores 0, regardless of what the board outcome would have earned it.
    if opponent_forged:
        score_map[opponent_group_name] = 0
    if we_forged:
        score_map[group_name] = 0
    group_ids = sorted([group_name, opponent_group_name])

    try:
        started_dt = datetime.fromisoformat(started)
        ended_dt = datetime.fromisoformat(ended)
        duration_seconds = max(0.0, (ended_dt - started_dt).total_seconds())
    except ValueError:
        duration_seconds = 0.0

    log_summary = {
        "sub_game_number": sub_game_number,
        "group_id": group_name,
        "role": "thief",
        "opponent_group_id": opponent_group_name,
        "result": result_word,
        "winner_role": _winner_role(winner, group_name),
        "steps": len(records),
        "timezone": DEFAULT_TIMEZONE,
        "started_at": started,
        "ended_at": ended,
        "duration_seconds": duration_seconds,
        "tokens_total": int(tokens_own),
        "audit": log_audit,
        "records": records,
    }

    sub_game = {
        "sub_game_number": sub_game_number,
        "roles": {group_name: "thief", opponent_group_name: "police"},
        "started_at": started,
        "ended_at": ended,
        "result": result_word,
        "winner_group": winner,
        "tie": False,
        "github_commit": {
            group_name: github_commit_own or "unknown",
            opponent_group_name: github_commit_opponent or "unknown",
        },
        "tokens": dict(tokens_map),
        "score": dict(score_map),
        "log_files": {
            group_name: log_filename(game_id, sub_game_number),
            opponent_group_name: log_filename(game_id, sub_game_number),
        },
        "audit": {"log_verified": log_verified, "tampered": not log_verified},
    }

    previous_result = load_previous_result(Path(results_dir) / result_filename(game_id))
    merged_sub_games = merge_sub_games(previous_result.get("sub_games", []), sub_game)
    final_result_aggregate = aggregate_series(merged_sub_games, group_name, opponent_group_name)
    tokens_total_series = tokens_series(merged_sub_games, group_ids)

    mutual_sha256 = consensus_signature(records)

    own_mcp = {"thief": own_mcp_url, "cop": own_mcp_url} if own_mcp_url else {}
    opp_mcp = (
        {"thief": opponent_mcp_url, "cop": opponent_mcp_url} if opponent_mcp_url else {}
    )

    shared_config_terms = (
        load_shared_config_terms(shared_config_path)
        if shared_config_path
        else {"board_and_agents": {"grid_size": int(config.require("board_and_agents.grid_size"))}}
    )

    max_tokens = config.get("network_and_league.token_budget_per_series")
    if max_tokens is None:
        max_tokens = 200000

    match_result = {
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "num_sub_games": num_sub_games,
        "group_ids": group_ids,
        "timezone": DEFAULT_TIMEZONE,
        "game_started_at": started,
        "game_ended_at": ended,
        "max_tokens_per_game": int(max_tokens),
        "own": {
            "group_id": group_name,
            "group_name": group_name,
            "members": own_members or [],
            "repos": dict(repos or {}),
            "mcp_servers": own_mcp,
            "llm_model": own_llm_model or config.get("llm.model", "template"),
            "hardware_spec": own_spec if own_spec is not None else sysinfo.collect_spec(),
            "team_code": own_team_code,
        },
        "opponent": {
            "group_id": opponent_group_name,
            "group_name": opponent_group_name,
            "members": opponent_members or [],
            "repos": dict(opponent_repos or {}),
            "mcp_servers": opp_mcp,
            "llm_model": opponent_llm_model,
            "hardware_spec": opponent_spec,
        },
        "shared_config_terms": shared_config_terms,
        "log_summary": log_summary,
        "sub_games": merged_sub_games,
        "final_result_aggregate": final_result_aggregate,
        "mutual_sha256": mutual_sha256,
    }

    # Rule 52 [FATAL]: exactly one counted game per opponent -- warm-ups
    # (is_counted=False) may repeat freely. A second *counted* attempt
    # against an opponent already recorded doesn't get a second league
    # credit, but the match's own report/audit/log still write in full
    # below; this is a league-bookkeeping guard, not a reason to lose the
    # documentation of what actually happened.
    league_counter = LeagueCounter(Path(results_dir) / "league_counter.json")
    already_counted = league_counter.games_played_against(opponent_group_name) > 0
    if is_counted and already_counted:
        print(
            f"[Warning] Rule 52: a counted game against {opponent_group_name!r} "
            f"was already recorded -- exactly one counted game per opponent is "
            f"allowed. This match's report is still written and sent in full, "
            f"but it will NOT be recorded as an additional counted game."
        )
    elif is_counted:
        league_counter.record_game(opponent_group_name)

    min_games_to_pass = config.get("network_and_league.min_games_to_pass")
    league_status = {
        "distinct_opponents_played": league_counter.distinct_opponents_played(),
        "min_games_to_pass": min_games_to_pass,
        "counted_this_game": bool(is_counted and not already_counted),
    }

    is_final_sub_game = sub_game_number >= num_sub_games
    write_and_send(
        match_result,
        gatekeeper,
        email_service,
        recipient,
        results_dir,
        league_counter,
        is_counted=is_counted,
        send_email=is_final_sub_game,
    )

    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "audit": {
            "passed": log_audit["passed"],
            "self_audited_by_opponent": self_audit,
            "opponent_audited_by_me": opponent_audit,
        },
        "final_result": {
            **final_result_aggregate,
            "tokens_total_series": tokens_total_series,
        },
        "league_status": league_status,
        "mutual_agreement": {
            "sha256": mutual_sha256,
            "confirmed": log_verified,
        },
    }
