"""finalize_match (PRD_8 §2.5): the end-of-match sequence -- submit_audit
exchange (skipped on a technical loss, since the whole reason we're here is
the opponent likely isn't responding) then report_writer.write_and_send.
Extracted out of `peer/runtime.py` as a free function for the same reason
as `peer/round_loop.py`: testability and file length.

Found while building this stage's two-real-instances integration test, two
real bugs neither surfaced until two independently-driven peers actually ran
together instead of one hand-wired smoke test:

1. `domain/game_ids.py`'s `derive_game_id(group_a, group_b)` is deliberately
   order-sensitive (`test_derive_game_id_distinguishes_the_two_group_orders`,
   Stage 6) -- calling it as `derive_game_id(my_group, their_group)`
   therefore makes each side compute a *different* game_id/game_uid for the
   same match, since each peer's "my group" is the other peer's "their
   group". Fixed by always sorting the two names before deriving the id, so
   both independently-built peers land on the identical id without needing
   any prior coordination -- `derive_game_id` itself is unchanged.
2. `report_writer.write_and_send`'s `league_counter` parameter defaults to
   `None`, which falls through to `LeagueCounter()`'s own default --
   `results/league_counter.json`, a path relative to the process's current
   working directory, *not* tied to this match's own `results_dir` at all.
   Every earlier caller (Stage 7's tests) happened to always pass an
   explicit `LeagueCounter`, so this never surfaced until this function
   omitted it -- caught here because running two real peers together wrote
   real files, unlike the earlier hand-wired single-sided smoke test. Fixed
   by always constructing `LeagueCounter` from this match's own
   `results_dir`, so nothing here can ever write outside it.

Found later, during a compliance re-audit against the book's Appendix E
(rules 19/36 -- mutual log audit): this function only ever submitted this
peer's own records to the opponent's `submit_audit` (getting audited BY
them) and never pulled the opponent's own revealed log to audit THEM --
the audit was one-directional, not mutual. Fixed by also calling the new
`get_revealed_records` tool and running `audit_records()` locally on
whatever comes back. Either direction failing overrides the natural
game-outcome winner (rule 19: "any hash mismatch at audit = automatic 0 to
the forging team," no appeal) -- catching the opponent lying wins
regardless of `end_reason`, and (should it ever happen with correct code)
being caught lying loses regardless of `end_reason` too.

`_NATIVE_STYLE_AUDIT_PROTOCOLS` is the extension point for this exchange:
`submit_audit`/`get_revealed_records` are this repo's own invented tool
names, so they only exist on a peer's server that also speaks this exact
vocabulary. A real Cop peer doesn't (her own end-of-match mechanism is
`receive_final_reveal`, wired separately -- `interop/cop_opponent.py::
send_opponent_final_reveal`, called before this function from
`peer/runtime.py`); a *different* future opponent registered in
`interop/cop_opponent.py` wouldn't either, unless it's added to this set
once its own audit exchange is confirmed compatible. Until then this
exchange is skipped entirely for it too, rather than calling tools that
don't exist on its server -- `audit.passed` reports "not evaluated," not a
false pass or false failure.
"""

from datetime import UTC, datetime
from pathlib import Path

from thief_peer.domain.crypto import audit_records
from thief_peer.domain.game_ids import derive_game_id, derive_game_uid
from thief_peer.domain.negotiation import canonical_terms
from thief_peer.domain.protocol import build_audit_payload
from thief_peer.domain.scoring import score_sub_game
from thief_peer.exceptions import ConfigError
from thief_peer.report.artifact_helpers import artifact_filenames
from thief_peer.report.report_writer import LeagueCounter, write_and_send

_SENDER = "thief"
_WINNER_IS_OPPONENT = {"technical_loss", "captured"}
_NATIVE_STYLE_AUDIT_PROTOCOLS = {"native"}
# Book's `result` enum is exactly capture|survival|timeout|tamper_forfeit --
# no slot for our own `technical_loss` (a protocol/deadline failure, not
# proven tampering). Mapped to "timeout" (Academic Freedom clause,
# documented in README.md): every technical-loss path here stems from a
# deadline/protocol-timing failure, not a rules violation.
# `max_moves_reached` maps to "survival", not "timeout": Table 2 (book
# §3.5, p.22) only has three rows -- capture / survival / technical loss
# -- and its "survival" condition is exactly "the thief survives
# survival_threshold valid steps without capture," which reaching the
# move cap uncaptured satisfies regardless of which check noticed it.
# (In this repo's own shared config survival_threshold == max_moves, so
# `has_survived` always fires first in practice -- this branch mainly
# matters if a differently-negotiated config ever set them apart.)
_RESULT_VALUE = {
    "captured": "capture",
    "survived": "survival",
    "max_moves_reached": "survival",
    "technical_loss": "timeout",
}


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
    started_at: str | None = None,
    our_github_commit: str | None = None,
    opponent_github_commit: str | None = None,
    technical_loss_reason: str | None = None,
    technical_loss_traceback: str | None = None,
) -> dict:
    # Every per-sub-game field below (roles, score, github_commit, tokens,
    # log_files) is a dict keyed by group name -- {group_name: ...,
    # opponent_group_name: ...} -- so an identical group_name on both sides
    # silently collapses to a single key (the second assignment overwrites
    # the first), and score_sub_game's `next(... role == "thief")` then
    # raises a bare, deep-in-the-stack StopIteration after the whole match
    # already played out. This only happens in a self-vs-self warm-up
    # (playing your own paired Cop, which legitimately shares your own real
    # group id) -- a real opponent always has a distinct group id -- but it
    # deserves a clear, actionable failure here rather than a confusing
    # crash after the match already ran to completion. Use a different
    # --group-name for a self-test (e.g. the local-test-double convention's
    # "dev-team"/"thief-team" pair) rather than your real, shared team id on
    # both sides.
    if group_name == opponent_group_name:
        raise ConfigError(
            f"Cannot finalize a report: this peer's own group_name "
            f"({group_name!r}) is identical to the opponent's declared "
            f"group_name -- the report schema requires two distinct group "
            f"ids (rule 49). If this is a self-test against your own paired "
            f"Cop, run it with a different --group-name than your real, "
            f"shared team id."
        )
    game_id = derive_game_id(*sorted([group_name, opponent_group_name]))
    game_uid = derive_game_uid(game_id, sub_game_number)
    result_claim = "technical_loss" if end_reason == "technical_loss" else "survival"

    _not_evaluated = {
        "passed": False,
        "verified_steps": 0,
        "failed_steps": [],
        "failed_capture_claims": [],
        "evaluated": False,
    }
    # cop_v1: Ch.5.3.2 Final Reveal carries nonces; both sides audit via
    # recomputed Hcommit (rules 19/36). `PeerRuntime` precomputes both
    # halves (her audit of us returned on our reveal call; our audit of
    # her after her reveal lands) and passes them here.
    if precomputed_self_audit is not None and precomputed_opponent_audit is not None:
        self_audit = precomputed_self_audit
        opponent_audit = precomputed_opponent_audit
        # Only treat as rule-19 material when at least one side actually
        # ran the Hcommit check (verified_steps>0 or failed_steps set).
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

    audit = {
        "passed": bool(self_audit.get("passed")) and bool(opponent_audit.get("passed")),
        "self_audited_by_opponent": self_audit,
        "opponent_audited_by_me": opponent_audit,
    }

    audit_override = False
    if (
        audit_was_evaluated
        and opponent_audit.get("evaluated", True)
        and not opponent_audit["passed"]
    ):
        winner = group_name  # caught the opponent forging -- automatic (rule 19)
        audit_override = True
    elif (
        audit_was_evaluated and self_audit.get("evaluated", True) and not self_audit["passed"]
    ):
        winner = opponent_group_name  # the opponent caught us forging -- automatic
        audit_override = True
    elif end_reason in _WINNER_IS_OPPONENT:
        winner = opponent_group_name
    else:
        winner = group_name
    final_result = {"winner_group": winner, "tokens_total_series": 0}

    filenames = artifact_filenames(game_id, sub_game_number)
    roles = {group_name: "thief", opponent_group_name: "cop"}
    result_value = "tamper_forfeit" if audit_override else _RESULT_VALUE[end_reason]
    # Table 2 (book §3.5, p.22): the negotiated scoring.* values, not a
    # hardcoded win/loss scheme -- falls back to this repo's own current
    # config's actual values only if the section is entirely absent
    # (e.g. a minimal test config), same pattern as the response_timeout_sec/
    # watchdog_timeout_sec fix (docs/todoFIXMCP.md Update 4).
    scoring = {
        "capture_cop": config.get("scoring.capture_cop", 20),
        "capture_thief": config.get("scoring.capture_thief", 5),
        "survival_cop": config.get("scoring.survival_cop", 5),
        "survival_thief": config.get("scoring.survival_thief", 10),
    }
    sub_game_entry = {
        "sub_game_number": sub_game_number,
        "roles": roles,
        "started_at": started_at or datetime.now(UTC).isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "result": result_value,
        "winner_group": winner,
        "tie": False,
        "is_counted": is_counted,
        "github_commit": {group_name: our_github_commit, opponent_group_name: opponent_github_commit},
        "tokens": {group_name: None, opponent_group_name: None},
        "score": score_sub_game(result_value, roles, scoring),
        "log_files": {group_name: filenames["log"], opponent_group_name: filenames["log"]},
        "audit": {
            "log_verified": bool(audit["passed"]) if audit_was_evaluated else False,
            "peer_audit_passed": bool(opponent_audit.get("passed")),
            "tampered": audit_was_evaluated and not audit["passed"],
        },
        # Diagnostic extension, not part of the book's schema (harmless
        # extra field, same precedent as games_played_including_this/
        # diversity_reward_applied): exactly which round/check failed and
        # when, and why -- previously print-only and lost the moment the
        # terminal scrolled past it (docs/todoFIXMCP.md). None for every
        # other end_reason. `technical_loss_traceback` is additionally
        # None even on a technical loss when the reason came from one of
        # play_round_cop's/play_round's own well-understood internal
        # checks (send failed / reveal never arrived) -- only populated
        # for a genuinely unexpected exception, where "which line raised
        # this" isn't otherwise inferable from the reason string alone.
        "technical_loss_reason": technical_loss_reason,
        "technical_loss_traceback": technical_loss_traceback,
    }

    match_result = {
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "num_sub_games": num_sub_games,
        "opponent_group_id": opponent_group_name,
        "groups": {
            "group_1": {"identity": group_name, "repos": repos or {}},
            "group_2": {"identity": opponent_group_name},
        },
        "shared_terms": canonical_terms(config),
        "config_name": f"config_{game_uid}",
        "records": records,
        "audit": audit,
        "final_result": final_result,
        "sub_game_entry": sub_game_entry,
        # docs/TodoCloseGaps.md #4: lecturer/league-management concerns --
        # confirmed not part of the book's own canonical result schema and
        # not read anywhere else in this codebase, but cheap to carry
        # through as bonus fields on the written report, same precedent as
        # games_played_including_this/diversity_reward_applied.
        "league_params": {
            "diversity_reward": config.get("network_and_league.diversity_reward"),
            "min_games_to_pass": config.get("network_and_league.min_games_to_pass"),
            "max_games_per_team": config.get("network_and_league.max_games_per_team"),
            "token_budget_per_series": config.get("network_and_league.token_budget_per_series"),
        },
    }
    league_counter = LeagueCounter(Path(results_dir) / "league_counter.json")
    write_and_send(
        match_result,
        gatekeeper,
        email_service,
        recipient,
        results_dir,
        league_counter,
        is_counted=is_counted,
    )

    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "audit": audit,
        "final_result": final_result,
        "groups": match_result["groups"],
    }
