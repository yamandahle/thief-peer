"""play_round (PRD_8 §2.5): one full commit/reveal round, driving turn_fsm
through its exact per-round cycle. Extracted out of `peer/runtime.py` as a
free function over explicit collaborators (matching this codebase's general
preference for pure/injectable functions over deep object coupling -- see
`peer/sealing.py`, `domain/negotiation.py`) both for testability and to keep
`runtime.py` itself under the file-length convention every other module here
already holds to.
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
) -> tuple[dict, dict, bool]:
    """Returns (sealed_record, next_opponent_scent, technical_loss)."""
    turn_fsm.transition("COMPUTING_MOVE")
    decision = turn_handler.play_turn(last_opponent_scent)
    decision.hint = trash_talk.generate_hint(step)
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
    send_reveal(transport, step, sender, decision, scent.snapshot())

    turn_fsm.transition("AWAITING_REVEAL")
    try:
        their_reveal = round_exchange.wait_for_reveal(step, round_deadline_sec)
    except DeadlineExceededError:
        turn_fsm.transition("TECHNICAL_LOSS")
        return record, last_opponent_scent, True

    turn_fsm.transition("VERIFYING")
    next_scent = their_reveal.get("scent_grid", {})
    turn_fsm.transition("WAITING_FOR_OPPONENT")
    return record, next_scent, False
