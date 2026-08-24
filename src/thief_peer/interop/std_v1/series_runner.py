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

import threading

from thief_peer.exceptions import DeadlineExceededError, SimulationError
from thief_peer.interop.std_v1.audit import (
    build_audit_envelope,
    build_consensus_envelope,
    build_consensus_object,
    build_sub_game_row,
    confirm_agreement,
    peer_github_commit,
    send_and_await,
    turn_records_only,
    validate_consensus_envelope,
    verify_peer_records,
)
from thief_peer.interop.std_v1.crypto import consensus_digest, derive_game_id, derive_game_uid
from thief_peer.interop.std_v1.handshake import negotiate_sub_game
from thief_peer.interop.std_v1.police_relay_loop import play_sub_game_as_police as play_sub_game_as_police_relay
from thief_peer.interop.std_v1.police_round_loop import play_sub_game_as_police
from thief_peer.interop.std_v1.replay_log import build_records
from thief_peer.interop.std_v1.report import build_result_report, now_iso
from thief_peer.interop.std_v1.report import final_result as build_final_result
from thief_peer.interop.std_v1.round_loop import play_sub_game
from thief_peer.interop.std_v1.roles import opposite_role, role_for_sub_game
from thief_peer.interop.std_v1.settlement_hash import settlement_hash

NATURAL_ROLE = "thief"

# yanell11, live: exchange.py's own instrumentation caught the peer's
# consensus envelope landing ~9-10s after send_and_await's own ceiling had
# already expired, twice, in back-to-back runs. This is a small, bounded,
# one-time grace check after the main wait gives up -- not a bigger
# ceiling, which already proved unreliable run-to-run for this opponent.
_CONSENSUS_GRACE_SEC = 15.0

# Section 6's real point table -- fixed by the rules, never negotiated.
_SCORE_TABLE = {
    "capture": {"police": 20, "thief": 5},
    "survival": {"police": 5, "thief": 10},
    "timeout": {"police": 0, "thief": 0},
    "technical_loss": {"police": 0, "thief": 0},
    "tamper_forfeit": {"police": 0, "thief": 0},
}


def _transport_for_role(role: str, transport, transport_when_police):
    """Some opponents (najamjad, live) run two genuinely separate processes
    behind two permanent, role-bound URLs -- `transport` carries every
    thief-role sub-game, `transport_when_police` (if given) every
    police-role one. `None` (the default) means every single-URL opponent's
    existing behavior is unchanged: `transport` for both roles."""
    if role == "thief" or transport_when_police is None:
        return transport
    return transport_when_police


def _their_final_games_played(their_games_played_including_this: int | None, is_counted: bool) -> int | None:
    """yanell11, live: the mirror image of a bug they found and fixed on
    their own side ("adds +1 for our own side but not for the opponent's").
    `games_played_including_this` (our own side, computed by the caller in
    std_v1_opponent.py) already gets the +1-for-this-game applied when
    `is_counted` -- the peer's own declared wire value (their prior count)
    needs the identical +1 applied here, not filed raw, or a counted game
    leaves their number one short of what their own report (and the
    agreed wire convention) says it should read. `None` (peer never
    declared one) stays `None` -- nothing to add 1 to."""
    if is_counted and their_games_played_including_this is not None:
        return their_games_played_including_this + 1
    return their_games_played_including_this


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
    except DeadlineExceededError:
        # yanell11, live: exchange.py's own diagnostics proved this exact
        # near-miss twice -- the peer's envelope gets stored by
        # record_audit (the inbound MCP handler, running on its own
        # thread) mere seconds after send_and_await's own deadline above
        # already expired and raised. The storage side has no timing gate
        # at all; only this read-side loop's own ceiling does. One cheap,
        # bounded, final direct check closes that exact gap -- not a
        # bigger ceiling (already shown unreliable run-to-run for this
        # opponent), a genuine last-chance look at whatever's already
        # sitting in `exchange` by the time we'd otherwise give up.
        try:
            peer_envelope = exchange.wait_for_consensus(_CONSENSUS_GRACE_SEC)
            peer_digest = validate_consensus_envelope(peer_envelope)
            print(
                f"[consensus] caught by the {_CONSENSUS_GRACE_SEC}s post-ceiling grace check "
                "-- the peer's envelope arrived just after our own wait window closed", flush=True,
            )
        except (DeadlineExceededError, SimulationError) as exc:
            print(f"[consensus] NOT CONFIRMED -- peer envelope never arrived or was invalid: {exc}", flush=True)
            return False, None
    except SimulationError as exc:
        print(f"[consensus] NOT CONFIRMED -- peer envelope never arrived or was invalid: {exc}", flush=True)
        return False, None
    agreed = confirm_agreement(all_clean, all_results_agreed, local_digest, peer_digest)
    print(
        f"[consensus] {'CONFIRMED' if agreed else 'NOT CONFIRMED'} -- "
        f"sha_match={local_digest == peer_digest} results_agreed={all_results_agreed} all_clean={all_clean}",
        flush=True,
    )
    return agreed, peer_digest


# najamjad/yanell11, live: `_resolve_consensus` above is documented as
# "NEVER raises" and internally bounded by `consensus_ceiling_sec` -- both
# true of its own control flow. Confirmed live anyway, a real hang: an
# outbound `McpTransport.call()` mid-flight when the peer's own consensus
# envelope arrived inbound within the same few seconds left the whole
# series stuck for 8+ minutes with zero further log activity, well past
# both the per-call `response_timeout_sec` (180s) and the outer
# `consensus_ceiling_sec` (600s) -- neither of `_resolve_consensus`'s own
# internal bounds ever fired; the process had to be killed by hand. Since
# the exact underlying cause (something below McpTransport's own
# documented timeout guarantees) isn't yet pinned down with certainty, this
# wraps the whole call in a genuine, un-defeatable wall-clock backstop
# instead of trusting the callee's own bookkeeping a second time -- a
# thread-join timeout is honored by the OS scheduler regardless of what the
# watched thread is actually doing, unlike an in-process asyncio/future
# timeout that depends on the stuck code's own cooperation.
_WATCHDOG_GRACE_SEC = 15.0


def _resolve_consensus_with_watchdog(
    transport,
    exchange,
    final_role: str,
    local_digest: str,
    resend_interval_sec: float,
    consensus_ceiling_sec: float,
    all_clean: bool,
    all_results_agreed: bool,
) -> tuple[bool, str | None]:
    result: list[tuple[bool, str | None]] = []

    def _run() -> None:
        result.append(
            _resolve_consensus(
                transport, exchange, final_role, local_digest,
                resend_interval_sec, consensus_ceiling_sec, all_clean, all_results_agreed,
            )
        )

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout=consensus_ceiling_sec + _WATCHDOG_GRACE_SEC)
    if result:
        return result[0]
    print(
        "[consensus] NOT CONFIRMED -- watchdog fired: _resolve_consensus did not "
        f"return within {consensus_ceiling_sec + _WATCHDOG_GRACE_SEC}s even though its own "
        f"internal ceiling is {consensus_ceiling_sec}s -- treating as unconfirmed rather than "
        "blocking the report/email pipeline indefinitely. The orphaned worker thread (daemon) "
        "keeps running in the background but can no longer affect this series' outcome.",
        flush=True,
    )
    return False, None


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
    consensus_ceiling_sec: float = 400.0,
    turn_fsm_factory=None,
    games_played_including_this: int = 0,
    counted_games_played: int | None = None,
    police_relay_transport=None,
    cop_github_commit: str | None = None,
    is_counted: bool = False,
    transport_when_police=None,
    natural_role: str = NATURAL_ROLE,
    first_meeting_between_groups: bool = True,
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
    number, not a second source of truth.

    `police_relay_transport`, if given, is an `infra/mcp_client.py::
    McpTransport` pointed at a separate `yamanagh-cop` process's loopback
    relay port (rule 1/2: real Police decisions must come from a genuinely
    separate process, not this repo's own built-in `police_brain.py`
    stand-in) -- every even sub-game then runs `police_relay_loop.py`
    instead of `police_round_loop.py`. `None` (the default) keeps the old
    built-in-stand-in path unchanged, so this is an opt-in switch, not a
    behavior change for anyone who hasn't wired a relay up yet.

    `transport_when_police`, if given, is a second `McpTransport` used for
    every wire call (negotiate/turn/audit) on sub-games where this side
    plays police, while `transport` continues to carry every thief-role
    sub-game -- some opponents (najamjad, live) run two genuinely separate
    processes behind two permanent, role-bound URLs rather than one shared
    endpoint, and expect the caller to address whichever of their two
    processes is on the other side of the current sub-game's role, not one
    fixed door for the whole series. `None` (the default) keeps every
    existing single-URL opponent's behavior byte-for-byte unchanged -- every
    sub-game, thief or police, uses the one `transport` already passed in.
    The final series-consensus exchange uses whichever of the two transports
    the *last* sub-game's role selected, on the reasoning that the peer
    process still on the other end of that same window is the one actually
    listening for it.

    `natural_role` defaults to this module's own `NATURAL_ROLE` ("thief"),
    matching every opponent seen so far -- but a real opponent (najamjad)
    turned out to be *also* unconditionally thief-first and refuses to
    swap, and nothing in `validate_offer` cross-checks a peer's declared
    role against ours, so two thief-first sides would silently play a
    meaningless series (no cop, nothing capturable) rather than fail
    loudly. The caller passes `"police"` for that one opponent; every other
    opponent's config is unaffected."""
    game_id = derive_game_id(my_group_id, their_group_id)
    game_uid = derive_game_uid(my_terms, my_group_id, their_group_id)
    max_steps = my_terms["max_steps"]
    thief_start = my_terms["thief_start"]

    rows: list[dict] = []
    sub_game_reports: list[dict] = []
    sub_game_meta: list[dict] = []
    all_records: list[dict] = []
    their_identity: dict = {}
    their_games_played_including_this: int | None = None
    all_clean = True
    game_started_at = now_iso()

    for sub_game_number in range(1, my_terms["num_games"] + 1):
        exchange.reset_turns()
        role = role_for_sub_game(natural_role, sub_game_number)
        active_transport = _transport_for_role(role, transport, transport_when_police)
        started_at = now_iso()
        their_offer = negotiate_sub_game(
            active_transport, exchange, my_terms, my_group_id, their_group_id,
            role, sub_game_number, identity, resend_interval_sec, negotiate_ceiling_sec,
            counted_games_played=counted_games_played,
        )
        their_identity = their_offer.get("identity", their_identity)
        # Peers put this at the top level of their own offer, inside
        # identity, or omit it entirely -- checked in that order, keeping
        # whatever this side last saw declared if a later sub-game's offer
        # doesn't repeat it, rather than treating a missing key as "reset
        # to unknown."
        their_games_played_including_this = (
            their_offer.get("counted_games_played")
            if their_offer.get("counted_games_played") is not None
            else their_identity.get("counted_games_played", their_games_played_including_this)
        )
        print(f"[negotiate] sub-game {sub_game_number} agreed OK -- we play {role}", flush=True)

        board = board_factory()
        state = state_factory(role)
        scent = scent_factory()
        turn_fsm = turn_fsm_factory() if turn_fsm_factory else None
        on_phase = turn_fsm.transition if turn_fsm else None

        if role == "thief":
            turn_handler = turn_handler_factory(board, state)
            end_reason, records, peer_commits, my_commits = play_sub_game(
                turn_handler, board, state, scent, trash_talk, active_transport, exchange,
                max_steps, turn_deadline_sec, on_phase,
                github_commit=identity.get("github_commit"),
            )
        elif police_relay_transport is not None:
            end_reason, records, peer_commits, my_commits = play_sub_game_as_police_relay(
                active_transport, exchange, max_steps, turn_deadline_sec,
                police_relay_transport, sub_game_number, on_phase,
                github_commit=cop_github_commit,
            )
        else:
            end_reason, records, peer_commits, my_commits = play_sub_game_as_police(
                board, state, scent, active_transport, exchange, max_steps, turn_deadline_sec,
                thief_start, on_phase,
                github_commit=identity.get("github_commit"),
            )
        all_records.extend(build_records(records, my_commits, sub_game_number))

        my_envelope = build_audit_envelope(role, records, end_reason, sub_game_number)
        # A slow/missing peer audit for THIS sub-game must not lose the
        # other five: real bug found live (ali-ahm1) -- this call had no
        # timeout handling at all, so one late audit response crashed the
        # whole series and threw away every sub-game already played,
        # including this one's own 35 real turns. Mirrors the final
        # series-consensus exchange's own graceful-degradation pattern
        # (series_runner.py's own consensus handling, a few lines below):
        # our own report is independently computed from our own
        # locally-verified data regardless of whether the peer's envelope
        # ever arrives -- a missing peer audit is "not verified", a real,
        # honest third state, never silently "verified OK" (an empty
        # records list would otherwise vacuously pass verify_peer_records)
        # and never a crash.
        try:
            peer_envelope = send_and_await(
                active_transport,
                lambda timeout, n=sub_game_number: exchange.wait_for_audit(n, timeout),
                my_envelope, resend_interval_sec, audit_ceiling_sec,
            )
        except DeadlineExceededError:
            peer_envelope = {}
            verify_result = {"log_verified": False, "tampered": False, "mismatched_steps": []}
            all_clean = False
            ended_at = now_iso()
            print(
                f"[sub-game {sub_game_number}] {end_reason} (role={role}) -- "
                f"peer audit NOT RECEIVED within {audit_ceiling_sec}s",
                flush=True,
            )
        else:
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
            # A peer's own sealed system_spec record, if it declares one,
            # wins over the negotiate-offer identity field -- reconciled
            # live against yanell11: their kit declares it there instead of
            # (or in addition to) identity.github_commit.
            "their_github_commit": peer_github_commit(peer_envelope.get("records", [])) or their_identity.get("github_commit"),
            # Rule 49/[REPORT] accuracy: a relayed Police sub-game was really
            # played by yamanagh-cop's own commit, not this process's -- only
            # substituted when the relay was actually used this sub-game
            # (role == "police" and a relay commit was actually fetched);
            # every other sub-game keeps attributing to this process's own
            # commit, since that's genuinely the code that played it.
            "my_github_commit": cop_github_commit if role == "police" and cop_github_commit else identity.get("github_commit"),
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
    final_result_obj = build_final_result(rows, my_group_id, their_group_id, games_played_including_this)
    # Section 11's own canonical-object digest ({game_id, game_uid,
    # sub_games}, compact separators, sort_keys=True) -- this repo's own
    # published guide (docs/NEXT_OPPONENT_INTEROP_GUIDE_PUBLIC.md #354-391)
    # documents this as *the* mutual_agreement.sha256 formula, and it's
    # what a spec-compliant opponent actually computes (proven live:
    # SMNGRP05's wire consensus_sha landed on this exact value, not the
    # settlement_hash formula this file used to send). A prior attempt to
    # reconcile against yanell11 by switching to settlement_hash instead
    # only "fixed" that one pairing because her own implementation also
    # deviates from the published guide -- it's not this repo's spec to
    # match a peer's deviation; it's the peer's bug if their digest doesn't
    # land on the documented formula. Diagnostic settlement_hash value kept
    # below for cross-checking, not sent on the wire.
    local_digest = consensus_digest(consensus_object)
    settlement_formula_digest = settlement_hash(game_id, final_result_obj, rows)
    all_results_agreed = all(
        report["peer_result_claim"] == report["end_reason"] for report in sub_game_reports
    )

    final_role = role_for_sub_game(natural_role, my_terms["num_games"])
    consensus_transport = _transport_for_role(final_role, transport, transport_when_police)
    agreed, peer_digest = _resolve_consensus_with_watchdog(
        consensus_transport, exchange, final_role, local_digest,
        resend_interval_sec, consensus_ceiling_sec, all_clean, all_results_agreed,
    )
    mutual_agreement = {
        "sha256": local_digest,
        "peer_sha256": peer_digest,
        "sha_match": local_digest == peer_digest,
        "results_agreed": all_results_agreed,
        "confirmed": agreed,
        "settlement_formula_sha256": settlement_formula_digest,
    }
    report = build_result_report(
        game_id, game_uid, my_group_id, their_group_id, identity, their_identity,
        rows, sub_game_meta, mutual_agreement, game_started_at, game_ended_at,
        games_played_including_this,
        _their_final_games_played(their_games_played_including_this, is_counted),
        is_counted=is_counted,
        first_meeting_between_groups=first_meeting_between_groups,
        num_sub_games=my_terms["num_games"],
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
