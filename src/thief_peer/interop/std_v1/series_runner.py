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

from thief_peer.exceptions import DeadlineExceededError, SimulationError
from thief_peer.interop.std_v1.audit import (
    build_audit_envelope,
    build_consensus_envelope,
    build_consensus_object,
    build_sub_game_row,
    confirm_agreement,
    send_and_await,
    turn_records_only,
    validate_consensus_envelope,
    verify_peer_records,
)
from thief_peer.interop.std_v1.crypto import consensus_digest, derive_game_id, derive_game_uid
from thief_peer.interop.std_v1.handshake import negotiate_sub_game
from thief_peer.interop.std_v1.police_round_loop import play_sub_game_as_police
from thief_peer.interop.std_v1.replay_log import build_records
from thief_peer.interop.std_v1.report import build_result_report, now_iso
from thief_peer.interop.std_v1.report import final_result as build_final_result
from thief_peer.interop.std_v1.round_loop import play_sub_game
from thief_peer.interop.std_v1.roles import opposite_role, role_for_sub_game
from thief_peer.interop.std_v1.settlement_hash import settlement_hash

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


def _resolve_consensus(
    transport,
    exchange,
    final_role: str,
    local_digest: str,
    resend_interval_sec: float,
    consensus_ceiling_sec: float,
    all_clean: bool,
    all_results_agreed: bool,
) -> tuple[bool, str | None]:
    """Runs the final consensus exchange and returns `(agreed, peer_digest)`
    -- NEVER raises. A missing or malformed peer envelope
    (DeadlineExceededError/SimulationError) is treated as `(False, None)`,
    not a fatal error that aborts the whole series -- confirmed live: a run
    with a clean 6/6 audited match on both sides still crashed the whole
    process right here (before this was caught), so the caller never
    reached write_std_v1_result/send_std_v1_report_email at all -- no
    report, no email, on ANY run so far, regardless of how clean the match
    actually was. Each side's own report is independently computed from
    its own locally-verified data (spec: "both teams independently build
    the final result JSON"); the peer's own envelope is confirmation of
    agreement, not a precondition for having a report to send at all."""
    try:
        peer_envelope = send_and_await(
            transport,
            lambda timeout: exchange.wait_for_consensus(timeout),
            build_consensus_envelope(final_role, local_digest),
            resend_interval_sec, consensus_ceiling_sec,
        )
        peer_digest = validate_consensus_envelope(peer_envelope)
    except (DeadlineExceededError, SimulationError) as exc:
        print(f"[consensus] NOT CONFIRMED -- peer envelope never arrived or was invalid: {exc}", flush=True)
        return False, None
    agreed = confirm_agreement(all_clean, all_results_agreed, local_digest, peer_digest)
    print(
        f"[consensus] {'CONFIRMED' if agreed else 'NOT CONFIRMED'} -- "
        f"sha_match={local_digest == peer_digest} results_agreed={all_results_agreed} all_clean={all_clean}",
        flush=True,
    )
    return agreed, peer_digest


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
    # Some peers only send their final series_consensus envelope some
    # time after their own result settles (reconciled live: yanell11's
    # own write-report-then-notify flow fires "a few seconds after
    # settlement", not synchronously) -- kept separate from the tighter
    # per-sub-game audit_ceiling_sec above rather than widening that too.
    consensus_ceiling_sec: float = 200.0,
    turn_fsm_factory=None,
    games_played_including_this: int = 0,
    counted_games_played: int | None = None,
) -> dict:
    """Runs every sub-game (1..`my_terms["num_games"]`) to completion, then
    the final series-consensus exchange. `board_factory()`/`scent_factory()`
    are role-independent; `state_factory(role)` returns a fresh
    `OwnGameState` positioned at the terms' own `thief_start`/`cop_start`
    for whichever role this sub-game alternates into; `turn_handler_factory
    (board, state)` is only ever used on Thief-role sub-games. Returns a
    summary dict with the consensus object, whether both sides agree, and
    each sub-game's own audit-verification result.

    `turn_fsm_factory()`, if given, is called once per sub-game (like the
    other factories) and must return a fresh object exposing `.transition
    (state_name)` (peer/turn_fsm.py::TurnFsm) -- its bound `.transition` is
    passed to the round loops as their optional `on_phase` observer, purely
    for a live GUI's turn-state display, never for control flow. A *fresh*
    instance every sub-game sidesteps TurnFsm's own strict, book-derived
    transition table (peer/turn_fsm.py's TRANSITIONS), which has no legal
    path from one sub-game's terminal state (e.g. after a capture) back to
    the next sub-game's opening WAITING_FOR_OPPONENT -- std_v1 plays many
    sub-games in one series where native only ever plays one match, so
    reusing a single TurnFsm across sub-game boundaries would raise on the
    very first transition of sub-game 2. Also collects this side's own
    revealed records into a single, replay-log-ready `all_records` list
    (see `replay_log.py::build_records`), returned so the caller can
    persist a `log_<game_uid>.json` the same way native's match loop does.

    `games_played_including_this` is threaded straight through to
    `report.py::build_result_report`'s own `final_result` -- computed by
    the caller (`interop/std_v1_opponent.py`, via the same `LeagueCounter`
    native's `report/report_writer.py` uses) before this call, since it
    depends on `results_dir`/`is_counted` bookkeeping this module has no
    reason to know about. `counted_games_played`, if given, is passed
    straight through to every per-sub-game `negotiate_sub_game` call so it
    lands at the top level of the wire offer too (yanell11, live: "we read
    it top-level, not inside identity") -- `identity` above already
    carries the same value under that same key (identity.py's own
    additive field), so this is a second placement of one already-computed
    number, not a second source of truth."""
    game_id = derive_game_id(my_group_id, their_group_id)
    game_uid = derive_game_uid(my_terms, my_group_id, their_group_id)
    max_steps = my_terms["max_steps"]
    thief_start = my_terms["thief_start"]

    rows: list[dict] = []
    sub_game_reports: list[dict] = []
    sub_game_meta: list[dict] = []
    all_records: list[dict] = []
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
            counted_games_played=counted_games_played,
        )
        their_identity = their_offer.get("identity", their_identity)
        print(f"[negotiate] sub-game {sub_game_number} agreed OK -- we play {role}", flush=True)

        board = board_factory()
        state = state_factory(role)
        scent = scent_factory()
        turn_fsm = turn_fsm_factory() if turn_fsm_factory else None
        on_phase = turn_fsm.transition if turn_fsm else None

        if role == "thief":
            turn_handler = turn_handler_factory(board, state)
            end_reason, records, peer_commits, my_commits = play_sub_game(
                turn_handler, board, state, scent, trash_talk, transport, exchange,
                max_steps, turn_deadline_sec, on_phase,
            )
        else:
            end_reason, records, peer_commits, my_commits = play_sub_game_as_police(
                board, state, scent, transport, exchange, max_steps, turn_deadline_sec,
                thief_start, on_phase,
            )
        all_records.extend(build_records(records, my_commits, sub_game_number))

        my_envelope = build_audit_envelope(role, records, end_reason, sub_game_number)
        peer_envelope = send_and_await(
            transport,
            lambda timeout, n=sub_game_number: exchange.wait_for_audit(n, timeout),
            my_envelope, resend_interval_sec, audit_ceiling_sec,
        )
        peer_records = turn_records_only(peer_envelope.get("records", []))
        verify_result = verify_peer_records(peer_records, peer_commits)
        all_clean = all_clean and verify_result["log_verified"]
        ended_at = now_iso()
        audit_state = "verified OK" if verify_result["log_verified"] else "TAMPERED"
        detail = f" mismatched_steps={verify_result['mismatched_steps']}" if verify_result["tampered"] else ""
        print(f"[sub-game {sub_game_number}] {end_reason} (role={role}) -- peer audit {audit_state}{detail}", flush=True)

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
            "steps": max(((r.get("payload") or {}).get("step", 0) for r in records), default=0),
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
    agreed, peer_digest = _resolve_consensus(
        transport, exchange, final_role, local_digest,
        resend_interval_sec, consensus_ceiling_sec, all_clean, all_results_agreed,
    )
    final_result_obj = build_final_result(rows, my_group_id, their_group_id, games_played_including_this)
    mutual_agreement = {
        "sha256": local_digest,
        "peer_sha256": peer_digest,
        "sha_match": local_digest == peer_digest,
        "results_agreed": all_results_agreed,
        "confirmed": agreed,
        # Not part of our own published interop guide's documented
        # mutual_agreement shape (docs/NEXT_OPPONENT_INTEROP_GUIDE_PUBLIC.md
        # #424: sha256/peer_sha256/sha_match/results_agreed/confirmed,
        # SHA-256 over {game_id, game_uid, sub_games}, compact separators)
        # -- yanell11's own kit hashes a *different* object ({game_id,
        # aggregate, sub_games-trimmed-to-5-fields}, spaced separators) and
        # calls that same result key "sha256" in her own report. Added
        # here as an extra, clearly-named field for her side to check
        # against, rather than overwriting our own documented `sha256`
        # value and silently breaking that contract for any other team
        # relying on the published guide.
        "settlement_sha256_yanell11_kit": settlement_hash(game_id, final_result_obj, rows),
    }
    report = build_result_report(
        game_id, game_uid, my_group_id, their_group_id, identity, their_identity,
        rows, sub_game_meta, mutual_agreement, game_started_at, game_ended_at,
        games_played_including_this,
    )

    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "records": all_records,
        "consensus_object": consensus_object,
        "consensus_sha": local_digest,
        "peer_consensus_sha": peer_digest,
        "agreed": agreed,
        "sub_games": sub_game_reports,
        "report": report,
    }
