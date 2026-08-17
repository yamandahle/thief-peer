"""play_series: the top-level std_v1 entry point (spec Section 10's full
match lifecycle) -- ties handshake.negotiate_sub_game, the per-sub-game
round loop, and audit.py's per-sub-game + final consensus exchange
together across all `num_games` sub-games. Section 6/10 [MATCH] role
alternation applies: odd sub-games (1,3,5) play this repo's natural
Thief role via round_loop.play_sub_game; even sub-games (2,4,6) flip to
the Police role via police_round_loop.play_sub_game_as_police (a
deliberately minimal brain -- see that module's own docstring).

`trash_talk` is a single collaborator built once for the whole series
(same lifetime as PeerRuntime's own `self.trash_talk`, not re-created
per sub-game) and threaded into every Thief-role play_sub_game call --
matching the native and cop_v1 protocols' own established pattern
(peer/round_loop.py, interop/cop_round_loop.py) of one long-lived
trash_talk instance reused across an entire match.

Scoring (`_row_for`) is the spec's own Section 6 table, fixed by the
rules and not negotiated: capture 20/5 (police/thief), survival 5/10,
and 0/0 for timeout/technical_loss/tamper_forfeit. `winner_group` is
null on a per-row score tie (Section 11) -- which is every zeroed
outcome, including tamper_forfeit, per Section 6's own "never count as
a scoring tie" framing applying at the series level, not overriding the
row-level null-on-tie rule.
"""

from __future__ import annotations

from thief_peer.interop.std_v1.audit import (
    build_audit_envelope,
    build_consensus_envelope,
    build_consensus_object,
    build_sub_game_row,
    confirm_agreement,
    send_and_await,
    validate_consensus_envelope,
    verify_peer_records,
)
from thief_peer.interop.std_v1.crypto import consensus_digest, derive_game_id, derive_game_uid
from thief_peer.interop.std_v1.handshake import negotiate_sub_game
from thief_peer.interop.std_v1.police_round_loop import play_sub_game_as_police
from thief_peer.interop.std_v1.report import build_result_report, now_iso
from thief_peer.interop.std_v1.round_loop import play_sub_game
from thief_peer.interop.std_v1.roles import opposite_role, role_for_sub_game

NATURAL_ROLE = "thief"

# Section 6's real point table -- fixed by the rules, never negotiated.
_SCORE_TABLE = {
    "capture": {"police": 20, "thief": 5},
    "survival": {"police": 5, "thief": 10},
    "timeout": {"police": 0, "thief": 0},
    "technical_loss": {"police": 0, "thief": 0},
    "tamper_forfeit": {"police": 0, "thief": 0},
}


def _row_for(
    sub_game_number: int, my_role: str, end_reason: str, tampered: bool, my_group_id: str, their_group_id: str
) -> dict:
    result = "tamper_forfeit" if tampered else end_reason
    their_role = opposite_role(my_role)
    points = _SCORE_TABLE[result]
    score = {my_group_id: points[my_role], their_group_id: points[their_role]}
    if score[my_group_id] == score[their_group_id]:
        winner = None
    else:
        winner = my_group_id if score[my_group_id] > score[their_group_id] else their_group_id
    roles = {my_group_id: my_role, their_group_id: their_role}
    return build_sub_game_row(sub_game_number, result, roles, score, winner)


def play_series(
    transport,
    exchange,
    my_terms: dict,
    my_group_id: str,
    their_group_id: str,
    identity: dict,
    board_factory,
    state_factory,
    turn_handler_factory,
    scent_factory,
    trash_talk,
    turn_deadline_sec: float = 10.0,
    resend_interval_sec: float = 2.0,
    negotiate_ceiling_sec: float = 300.0,
    audit_ceiling_sec: float = 60.0,
) -> dict:
    """Runs every sub-game (1..`my_terms["num_games"]`) to completion, then
    the final series-consensus exchange. `board_factory()`/`scent_factory()`
    are role-independent; `state_factory(role)` returns a fresh
    `OwnGameState` positioned at the terms' own `thief_start`/`cop_start`
    for whichever role this sub-game alternates into; `turn_handler_factory
    (board, state)` is only ever used on Thief-role sub-games. Returns a
    summary dict with the consensus object, whether both sides agree, and
    each sub-game's own audit-verification result."""
    game_id = derive_game_id(my_group_id, their_group_id)
    game_uid = derive_game_uid(my_terms, my_group_id, their_group_id)
    max_steps = my_terms["max_steps"]
    thief_start = my_terms["thief_start"]

    rows: list[dict] = []
    sub_game_reports: list[dict] = []
    sub_game_meta: list[dict] = []
    their_identity: dict = {}
    all_clean = True
    game_started_at = now_iso()

    for sub_game_number in range(1, my_terms["num_games"] + 1):
        exchange.reset_turns()
        role = role_for_sub_game(NATURAL_ROLE, sub_game_number)
        started_at = now_iso()
        their_offer = negotiate_sub_game(
            transport, exchange, my_terms, my_group_id, their_group_id,
            role, sub_game_number, identity, resend_interval_sec, negotiate_ceiling_sec,
        )
        their_identity = their_offer.get("identity", their_identity)

        board = board_factory()
        state = state_factory(role)
        scent = scent_factory()

        if role == "thief":
            turn_handler = turn_handler_factory(board, state)
            end_reason, records, peer_commits = play_sub_game(
                turn_handler, board, state, scent, trash_talk, transport, exchange, max_steps, turn_deadline_sec
            )
        else:
            end_reason, records, peer_commits = play_sub_game_as_police(
                board, state, scent, transport, exchange, max_steps, turn_deadline_sec, thief_start
            )

        my_envelope = build_audit_envelope(role, records, end_reason, sub_game_number)
        peer_envelope = send_and_await(
            transport,
            lambda timeout, n=sub_game_number: exchange.wait_for_audit(n, timeout),
            my_envelope, resend_interval_sec, audit_ceiling_sec,
        )
        verify_result = verify_peer_records(peer_envelope.get("records", []), peer_commits)
        all_clean = all_clean and verify_result["log_verified"]
        ended_at = now_iso()

        rows.append(_row_for(sub_game_number, role, end_reason, verify_result["tampered"], my_group_id, their_group_id))
        sub_game_reports.append({
            "sub_game_number": sub_game_number,
            "role": role,
            "end_reason": end_reason,
            "peer_result_claim": peer_envelope.get("result_claim"),
            "verify": verify_result,
        })
        sub_game_meta.append({
            "their_github_commit": their_identity.get("github_commit"),
            "steps": max((r.get("step", 0) for r in records), default=0),
            "started_at": started_at,
            "ended_at": ended_at,
            "audit": {
                "log_verified": verify_result["log_verified"],
                "tampered": verify_result["tampered"],
                "result_agreed": peer_envelope.get("result_claim") == end_reason,
            },
        })

    game_ended_at = now_iso()
    consensus_object = build_consensus_object(game_id, game_uid, rows)
    local_digest = consensus_digest(consensus_object)
    all_results_agreed = all(
        report["peer_result_claim"] == report["end_reason"] for report in sub_game_reports
    )

    final_role = role_for_sub_game(NATURAL_ROLE, my_terms["num_games"])
    peer_envelope = send_and_await(
        transport,
        lambda timeout: exchange.wait_for_consensus(timeout),
        build_consensus_envelope(final_role, local_digest),
        resend_interval_sec, audit_ceiling_sec,
    )
    peer_digest = validate_consensus_envelope(peer_envelope)
    agreed = confirm_agreement(all_clean, all_results_agreed, local_digest, peer_digest)
    mutual_agreement = {
        "sha256": local_digest,
        "peer_sha256": peer_digest,
        "sha_match": local_digest == peer_digest,
        "results_agreed": all_results_agreed,
        "confirmed": agreed,
    }
    report = build_result_report(
        game_id, game_uid, my_group_id, their_group_id, identity, their_identity,
        rows, sub_game_meta, mutual_agreement, game_started_at, game_ended_at,
    )

    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "consensus_object": consensus_object,
        "consensus_sha": local_digest,
        "peer_consensus_sha": peer_digest,
        "agreed": agreed,
        "sub_games": sub_game_reports,
        "report": report,
    }
