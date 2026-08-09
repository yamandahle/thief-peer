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
"""

from pathlib import Path

from thief_peer.domain.crypto import audit_records
from thief_peer.domain.game_ids import derive_game_id, derive_game_uid
from thief_peer.domain.negotiation import canonical_terms
from thief_peer.domain.protocol import build_audit_payload
from thief_peer.report.report_writer import LeagueCounter, write_and_send

_SENDER = "thief"
_WINNER_IS_OPPONENT = {"technical_loss", "captured"}


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
) -> dict:
    game_id = derive_game_id(*sorted([group_name, opponent_group_name]))
    game_uid = derive_game_uid(game_id, sub_game_number)
    result_claim = "technical_loss" if end_reason == "technical_loss" else "survival"

    _not_evaluated = {"passed": False, "verified_steps": 0, "failed_steps": []}
    # A real Cop peer has no submit_audit/get_revealed_records tools -- her
    # per-turn commit envelope is cryptographically incompatible with this
    # side's own anyway (interop/__init__.py's documented scope boundary),
    # so this exchange is skipped entirely rather than calling tools that
    # don't exist on her server.
    if end_reason == "technical_loss" or opponent_protocol != "native":
        self_audit = _not_evaluated
        opponent_audit = _not_evaluated
    else:
        # Get audited BY the opponent (submit our own revealed log to them).
        audit_payload = build_audit_payload(_SENDER, result_claim, records)
        self_audit = transport.call("submit_audit", {"payload": audit_payload})

        # Actively audit THEM: pull their revealed log and verify it
        # ourselves, rather than only ever being the one getting checked.
        their_records = transport.call("get_revealed_records", {"payload": {}})["records"]
        opponent_audit = audit_records(their_records)

    audit = {
        "passed": self_audit["passed"] and opponent_audit["passed"],
        "self_audited_by_opponent": self_audit,
        "opponent_audited_by_me": opponent_audit,
    }

    audit_was_evaluated = end_reason != "technical_loss" and opponent_protocol == "native"
    if audit_was_evaluated and not opponent_audit["passed"]:
        winner = group_name  # caught the opponent forging -- automatic (rule 19)
    elif audit_was_evaluated and not self_audit["passed"]:
        winner = opponent_group_name  # the opponent caught us forging -- automatic
    elif end_reason in _WINNER_IS_OPPONENT:
        winner = opponent_group_name
    else:
        winner = group_name
    final_result = {"winner_group": winner, "tokens_total_series": 0}

    match_result = {
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "num_sub_games": num_sub_games,
        "opponent_group_id": opponent_group_name,
        "groups": {
            # Rule 49 ("four links in both teams' JSON"): only this peer's
            # own known repos -- the opponent's are genuinely unknowable
            # over this wire (no channel exists), never invented.
            "group_1": {"identity": group_name, "repos": repos or {}},
            "group_2": {"identity": opponent_group_name},
        },
        "shared_terms": canonical_terms(config),
        "config_name": f"config_{game_uid}",
        "records": records,
        "audit": audit,
        "final_result": final_result,
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
