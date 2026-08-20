"""Per-sub-game turn loop for std_v1's Thief role (spec Sections 5, 9, 10)
-- this repo's natural role, used on odd sub-games always and on even
ones too unless role alternation (Section 6) flips this side to Police
for that sub-game (see police_round_loop.py).

Step numbering is per-peer, not a shared global counter: a "round" is one
Thief message plus one Police reply carrying the *same* step number, each
side's own counter incrementing by 1 every time it sends. `max_steps` = 35
means 35 rounds -- the Thief's own step reaching 35 is its survival claim.
This is a real interop convention that isn't fully pinned by the spec text
this repo was originally built against; reconciled empirically against a
real opponent (yanell11) after their real, hash-agreed matches against
three other teams all used per-peer numbering, and this repo's own
Appendix-D-based argument for a shared counter turned out not to actually
disambiguate the two conventions on reflection (both produce "step 35" on
the Thief's own final message). Since a peer never has to be authoritative
across the whole class -- only vs. whoever it's actually negotiating with
-- and per-peer numbering is what's proven itself compatible in practice
this session, that's what this loop now speaks.

Movement comes from this repo's own real strategy stack --
`turn_handler.play_turn(last_cop_scent)` (peer/turn_handler.py, one
positional argument only) followed by `trash_talk.generate_hint(step)`,
exactly the same two-call pattern peer/round_loop.py::play_round and
interop/cop_round_loop.py::play_round_cop already use for the native and
cop_v1 protocols -- std_v1 gets this repo's actual belief/pursuit
strategy for free rather than a second, weaker implementation.
algorithm-enhancements' own reference version instead threaded the Cop's
last hint text into a 3-argument play_turn(scent, hint, own_scent=...)
signature belonging to their own upgraded ThiefBrain; this repo's brain
never consumes hint text for belief updates (only scent), so that
argument is simply dropped here, matching how the native and cop_v1
loops already treat the opponent's hint as informational-only.
"""

from __future__ import annotations

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.interop.std_v1.capture import build_claim_response, evaluate_capture
from thief_peer.interop.std_v1.sealing import (
    build_audit_record,
    build_step0_record,
    build_turn_message,
    build_turn_payload,
    seal_turn,
)
from thief_peer.interop.std_v1.wire import send_turn


def _move_token(direction) -> str:
    return direction.value if direction is not None else "STAY"


def play_sub_game(
    turn_handler,
    board,
    state,
    scent,
    trash_talk,
    transport,
    exchange,
    max_steps: int,
    turn_deadline_sec: float,
    on_phase=None,
    github_commit: str | None = None,
) -> tuple[str, list[dict], dict[int, str], dict[int, str]]:
    """Returns (result, records, peer_commits, my_commits) -- `result` is one
    of "capture"/"survival"/"timeout", mirroring police_round_loop.py's own
    return shape so series_runner.py can treat both roles uniformly.
    `records` are this side's own revealed turns (for its own
    submit_audit); `peer_commits` are the Cop's live commits, keyed by
    step, kept for verify_peer_records to check against the Cop's later-
    revealed records; `my_commits` are this side's own live commits, keyed
    by step, kept so a replay log can pair each revealed record with the
    commit it was actually sealed under.

    `github_commit`, if given, seeds a sealed step-0 declaration record as
    `records[0]` (see `sealing.py::build_step0_record`'s own docstring for
    why this exists) -- a real peer-audit gap found live, since without it
    a peer's own report has nothing to read our commit off of no matter
    how correct our negotiate-offer identity is.

    `on_phase`, if given, is called with one of TurnFsm's own state names
    (peer/turn_fsm.py) at each of that book state machine's transition
    points -- this loop's actual sequence (compute -> commit -> await
    reveal -> verify -> repeat) is already exactly that cycle, so this is
    purely an optional observation hook (e.g. for a live GUI's turn
    banner), never consulted for control flow."""

    def _phase(name: str) -> None:
        if on_phase is not None:
            on_phase(name)

    records: list[dict] = [build_step0_record("thief", github_commit)]
    peer_commits: dict[int, str] = {}
    my_commits: dict[int, str] = {}
    last_cop_scent: dict[str, float] = {}
    last_cop_declared_position: tuple[int, int] | None = None
    last_cop_declared_radius = 0
    pending_claim_response: dict | None = None

    step = 1
    while step <= max_steps:
        _phase("COMPUTING_MOVE")
        decision = turn_handler.play_turn(
            last_cop_scent, last_cop_declared_position, last_cop_declared_radius
        )
        decision.hint = trash_talk.generate_hint(step)
        win_claim = {"type": "survival"} if step == max_steps else None
        payload = build_turn_payload(
            step=step,
            sender="thief",
            move=_move_token(decision.direction),
            hint=decision.hint,
            smell_grid=scent.snapshot(),
            claim_response=pending_claim_response,
            win_claim=win_claim,
        )
        sealed = seal_turn(payload)
        records.append(build_audit_record(payload, sealed["nonce"], sealed["commit"]))
        my_commits[step] = sealed["commit"]
        _phase("COMMITTING")
        send_turn(transport, build_turn_message(payload, sealed["commit"]))
        print(f"[turn {step}] sent move={payload['move']}" + (" (survival claim)" if win_claim else ""), flush=True)
        scent.advance(state.position)
        pending_claim_response = None

        if win_claim is not None:
            return "survival", records, peer_commits, my_commits

        _phase("AWAITING_REVEAL")
        try:
            cop_message = exchange.wait_for_turn(step, timeout=turn_deadline_sec)
        except DeadlineExceededError:
            return "timeout", records, peer_commits, my_commits
        peer_commits[cop_message["step"]] = cop_message["commit"]
        print(f"[turn {cop_message['step']}] received police reply", flush=True)

        barrier_placed = cop_message.get("barrier_placed")
        if barrier_placed is not None:
            state.record_barrier(tuple(barrier_placed))
        # PLAN.md Stage 7.4: the Cop's own stated cell, folded into next
        # turn's belief as a direct-evidence declaration -- capture_claim
        # (radius 0, exact) takes priority over barrier_placed (radius 1,
        # only pins the Cop within one cell) when both are present, since
        # it's the stronger signal.
        capture_claim = cop_message.get("capture_claim")
        if capture_claim is not None:
            last_cop_declared_position, last_cop_declared_radius = tuple(capture_claim), 0
        elif barrier_placed is not None:
            last_cop_declared_position, last_cop_declared_radius = tuple(barrier_placed), 1
        else:
            last_cop_declared_position, last_cop_declared_radius = None, 0
        _phase("VERIFYING")
        caught = evaluate_capture(state, board, capture_claim, barrier_placed)
        claim_response = build_claim_response(capture_claim, caught)
        if claim_response is None and caught:
            # Captured via barrier/stuck (conditions B/C) on a turn the Cop
            # made no landing claim at all -- there's still a truthful cell
            # to confirm, our own actual position, even though the Cop's
            # own capture_claim was absent this turn.
            claim_response = {"claim": list(state.position), "caught": True}

        if caught:
            # Section 5: the Thief still owes one final turn message
            # carrying the truthful claim_response before the sub-game
            # ends -- STAY, since there is no further move to make.
            # Per-peer numbering: this is still this side's own next step.
            final_step = step + 1
            final_payload = build_turn_payload(
                step=final_step,
                sender="thief",
                move="STAY",
                hint="",
                smell_grid=scent.snapshot(),
                claim_response=claim_response,
            )
            final_sealed = seal_turn(final_payload)
            records.append(build_audit_record(final_payload, final_sealed["nonce"], final_sealed["commit"]))
            my_commits[final_step] = final_sealed["commit"]
            send_turn(transport, build_turn_message(final_payload, final_sealed["commit"]))
            return "capture", records, peer_commits, my_commits

        pending_claim_response = claim_response
        last_cop_scent = cop_message.get("smell_grid") or {}
        _phase("WAITING_FOR_OPPONENT")
        step += 1

    return "survival", records, peer_commits, my_commits
