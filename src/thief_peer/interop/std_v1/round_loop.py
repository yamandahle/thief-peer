"""Per-sub-game turn loop for std_v1's Thief role (spec Sections 5, 9, 10)
-- this repo's natural role, used on odd sub-games always and on even
ones too unless role alternation (Section 6) flips this side to Police
for that sub-game (see police_round_loop.py).

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

    `on_phase`, if given, is called with one of TurnFsm's own state names
    (peer/turn_fsm.py) at each of that book state machine's transition
    points -- this loop's actual sequence (compute -> commit -> await
    reveal -> verify -> repeat) is already exactly that cycle, so this is
    purely an optional observation hook (e.g. for a live GUI's turn
    banner), never consulted for control flow."""

    def _phase(name: str) -> None:
        if on_phase is not None:
            on_phase(name)

    records: list[dict] = []
    peer_commits: dict[int, str] = {}
    my_commits: dict[int, str] = {}
    last_cop_scent: dict[str, float] = {}
    pending_claim_response: dict | None = None

    step = 1
    while step <= max_steps:
        _phase("COMPUTING_MOVE")
        decision = turn_handler.play_turn(last_cop_scent)
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
        records.append(build_audit_record(payload, sealed["nonce"]))
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
            cop_message = exchange.wait_for_turn(step + 1, timeout=turn_deadline_sec)
        except DeadlineExceededError:
            return "timeout", records, peer_commits, my_commits
        peer_commits[cop_message["step"]] = cop_message["commit"]
        print(f"[turn {cop_message['step']}] received police reply", flush=True)

        barrier_placed = cop_message.get("barrier_placed")
        if barrier_placed is not None:
            state.record_barrier(tuple(barrier_placed))
        _phase("VERIFYING")
        caught = evaluate_capture(state, board, cop_message["capture_claim"], barrier_placed)
        claim_response = build_claim_response(cop_message["capture_claim"], caught)

        if caught:
            # Section 5: the Thief still owes one final turn message
            # carrying the truthful claim_response before the sub-game
            # ends -- STAY, since there is no further move to make.
            final_step = step + 2
            final_payload = build_turn_payload(
                step=final_step,
                sender="thief",
                move="STAY",
                hint="",
                smell_grid=scent.snapshot(),
                claim_response=claim_response,
            )
            final_sealed = seal_turn(final_payload)
            records.append(build_audit_record(final_payload, final_sealed["nonce"]))
            my_commits[final_step] = final_sealed["commit"]
            send_turn(transport, build_turn_message(final_payload, final_sealed["commit"]))
            return "capture", records, peer_commits, my_commits

        pending_claim_response = claim_response
        last_cop_scent = cop_message.get("smell_grid") or {}
        _phase("WAITING_FOR_OPPONENT")
        step += 2

    return "survival", records, peer_commits, my_commits
