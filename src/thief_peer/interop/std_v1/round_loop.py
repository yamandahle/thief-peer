"""Per-sub-game turn loop for the std_v1 protocol's Thief role (spec
Sections 5, 9, 10).

A single shared, alternating step counter, not two independent per-side
counters: the Thief sends odd-numbered steps, the Cop even-numbered ones.
Appendix D's own worked example confirms this reading -- step 4 is a
police turn, step 35 (the survival threshold) is a thief turn, consistent
with "the Thief sends the first turn of each sub-game" and a 35-*turn*
sub-game (not 35 moves per side independently, ~70 messages).

Reuses this repo's own TurnHandler/ThiefBrain/ScentField exactly as the
native and cop_v1 protocols already do -- only the wire format and turn
cadence differ here, never the actual decision-making.
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
    transport,
    exchange,
    max_steps: int,
    turn_deadline_sec: float,
) -> tuple[str, list[dict], dict[int, str]]:
    """Returns (end_reason, records, peer_commits): end_reason is one of
    "capture", "survival", "timeout" -- `records` is this side's own
    sealed turn history (payload + nonce, `move` included), ready for the
    per-sub-game audit exchange. `peer_commits` is `{step: commit}` for
    every Cop turn actually received live -- the audit step verifies the
    peer's later-revealed records against these, not against whatever the
    peer merely *claims* it sent."""
    records: list[dict] = []
    peer_commits: dict[int, str] = {}
    last_cop_scent: dict[str, float] = {}
    last_cop_hint: str = ""
    pending_claim_response: dict | None = None

    step = 1
    while step <= max_steps:
        decision = turn_handler.play_turn(
            last_cop_scent, last_cop_hint, own_scent_snapshot=scent.snapshot()
        )
        move = _move_token(decision.direction)
        win_claim = {"type": "survival"} if step == max_steps else None
        payload = build_turn_payload(
            step=step,
            sender="thief",
            move=move,
            hint=decision.hint,
            smell_grid=scent.snapshot(),
            claim_response=pending_claim_response,
            win_claim=win_claim,
        )
        sealed = seal_turn(payload)
        records.append(build_audit_record(payload, sealed["nonce"]))
        send_turn(transport, build_turn_message(payload, sealed["commit"]))
        scent.advance(state.position)
        pending_claim_response = None  # answered; never resend a stale one

        if win_claim is not None:
            return "survival", records, peer_commits

        try:
            cop_message = exchange.wait_for_turn(step + 1, timeout=turn_deadline_sec)
        except DeadlineExceededError:
            return "timeout", records, peer_commits
        peer_commits[cop_message["step"]] = cop_message["commit"]

        barrier_placed = cop_message.get("barrier_placed")
        if barrier_placed is not None:
            state.record_barrier(tuple(barrier_placed))
        caught = evaluate_capture(state, board, cop_message["capture_claim"], barrier_placed)
        claim_response = build_claim_response(cop_message["capture_claim"], caught)

        if caught:
            # Section 5: a caught Thief still owes one final sealed
            # no-move STAY carrying the truthful answer -- "MUST NOT make
            # a further gameplay move", not "must not answer at all".
            final_step = step + 1
            final_payload = build_turn_payload(
                step=final_step, sender="thief", move="STAY", hint="",
                smell_grid=scent.snapshot(), claim_response=claim_response,
            )
            final_sealed = seal_turn(final_payload)
            records.append(build_audit_record(final_payload, final_sealed["nonce"]))
            send_turn(transport, build_turn_message(final_payload, final_sealed["commit"]))
            return "capture", records, peer_commits

        pending_claim_response = claim_response
        last_cop_scent = cop_message.get("smell_grid") or {}
        last_cop_hint = cop_message.get("hint") or ""
        step += 2

    return "survival", records, peer_commits
