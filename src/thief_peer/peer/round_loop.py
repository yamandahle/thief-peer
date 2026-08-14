"""play_round (PRD_8 §2.5): one full commit/reveal round, driving turn_fsm
through its exact per-round cycle. Extracted out of `peer/runtime.py` as a
free function over explicit collaborators (matching this codebase's general
preference for pure/injectable functions over deep object coupling -- see
`peer/sealing.py`, `domain/negotiation.py`) both for testability and to keep
`runtime.py` itself under the file-length convention every other module here
already holds to.

Book Fig. 6 (p.35-36, ch.5.3.2) names four steps -- Commit, Acknowledge,
Reveal, Final Audit -- specifically so neither side reveals before both
are already locked in. This function used to send its own reveal
immediately after its own commit, with no wait in between: a slow or
dishonest opponent could see this side's revealed move before committing
their own, the exact "change your move after seeing theirs" attack the
whole protocol exists to prevent. Fixed by waiting on
`round_exchange.wait_for_commit()` (already built, previously unused)
before calling `send_reveal`. The book's own transition table (Ch.8 p.63)
has no `COMMITTING -> TECHNICAL_LOSS` edge -- only `AWAITING_REVEAL ->
TECHNICAL_LOSS` -- so a commit-wait timeout takes the same two-step
detour through `AWAITING_REVEAL` that `interop/cop_round_loop.py`'s own
send-failure handling already established for the identical reason.
"""

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.peer.sealing import sealed_step_record
from thief_peer.peer.turn_sender import send_commit, send_reveal


def play_round(
    step: int,
    turn_handler,
    turn_fsm,
    scent,
    trash_talk,
    round_exchange,
    transport,
    sender: str,
    round_deadline_sec: float,
    last_opponent_scent: dict,
    last_opponent_hint: str = "",
) -> tuple[dict, dict, str, bool]:
    """Returns (sealed_record, next_opponent_scent, next_opponent_hint, technical_loss)."""
    turn_fsm.transition("COMPUTING_MOVE")
    decision = turn_handler.play_turn(
        last_opponent_scent, last_opponent_hint, own_scent_snapshot=scent.snapshot()
    )
    decision.hint = trash_talk.generate_hint(step, decision.verdict)
    scent.advance(turn_handler.state.position)

    move = decision.direction.value if decision.direction else "STAY"
    record = sealed_step_record(
        state=f"step-{step}",
        move=move,
        intent=decision.verdict,
        hint_text=decision.hint,
        step=step,
        role=sender,
    )

    turn_fsm.transition("COMMITTING")
    send_commit(transport, step, sender, record)
    try:
        round_exchange.wait_for_commit(step, round_deadline_sec)
    except DeadlineExceededError:
        turn_fsm.transition("AWAITING_REVEAL")
        turn_fsm.transition("TECHNICAL_LOSS")
        return record, last_opponent_scent, last_opponent_hint, True
    send_reveal(transport, step, sender, decision, scent.snapshot())

    turn_fsm.transition("AWAITING_REVEAL")
    try:
        their_reveal = round_exchange.wait_for_reveal(step, round_deadline_sec)
    except DeadlineExceededError:
        turn_fsm.transition("TECHNICAL_LOSS")
        return record, last_opponent_scent, last_opponent_hint, True

    turn_fsm.transition("VERIFYING")
    next_scent = their_reveal.get("scent_grid", {})
    next_hint = their_reveal.get("hint", "")
    turn_fsm.transition("WAITING_FOR_OPPONENT")
    return record, next_scent, next_hint, False
