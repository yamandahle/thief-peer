"""play_round (PRD_8 §2.5): one full commit/reveal round, driving turn_fsm
through its exact per-round cycle. Extracted out of `peer/runtime.py` as a
free function over explicit collaborators (matching this codebase's general
preference for pure/injectable functions over deep object coupling -- see
`peer/sealing.py`, `domain/negotiation.py`) both for testability and to keep
`runtime.py` itself under the file-length convention every other module here
already holds to.
"""

from thief_peer.exceptions import DeadlineExceededError, TransportError
from thief_peer.peer.sealing import sealed_step_record
from thief_peer.peer.strategy_deadline import run_with_deadline
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
    strategy_deadline_sec: float,
    last_opponent_scent: dict,
    round_wakeup=None,
) -> tuple[dict, dict, bool, str | None]:
    """Returns (sealed_record, next_opponent_scent, technical_loss, reason).
    `reason` is None unless `technical_loss` is True (docs/todoFIXMCP.md)."""
    turn_fsm.transition("COMPUTING_MOVE")

    def _compute_move():
        decision = turn_handler.play_turn(last_opponent_scent)
        decision.hint = trash_talk.generate_hint(step)
        return decision

    # Not caught here: unlike the network-deadline catch below, there is no
    # sealed record yet to return on a strategy-computation timeout -- let
    # it propagate to PeerRuntime.run()'s outer wrapper, which already
    # handles "no record for this round" correctly.
    decision = run_with_deadline(_compute_move, strategy_deadline_sec)
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
    try:
        send_commit(transport, step, sender, record)
        send_reveal(transport, step, sender, decision, scent.snapshot())
    except (DeadlineExceededError, TransportError) as exc:
        # docs/todoFIXMCP.md: this was unguarded here (unlike the cop_v1
        # round loop's identical send-then-reveal pair, which already
        # catches this) -- a transport failure here previously propagated
        # straight to PeerRuntime.run()'s outer catch-all with no sealed
        # record, when the book's own transition table has a dedicated
        # AWAITING_REVEAL -> TECHNICAL_LOSS edge for exactly this case.
        turn_fsm.transition("AWAITING_REVEAL")
        turn_fsm.transition("TECHNICAL_LOSS")
        return (
            record,
            last_opponent_scent,
            True,
            f"commit/reveal send failed: {type(exc).__name__}: {exc}",
        )

    turn_fsm.transition("AWAITING_REVEAL")
    try:
        their_reveal = round_exchange.wait_for_reveal(step, round_deadline_sec, interrupt=round_wakeup)
    except DeadlineExceededError as exc:
        turn_fsm.transition("TECHNICAL_LOSS")
        return (
            record,
            last_opponent_scent,
            True,
            f"opponent's reveal never arrived: {type(exc).__name__}: {exc}",
        )

    turn_fsm.transition("VERIFYING")
    # their_reveal is None when round_wakeup fired instead of a real reveal
    # arriving (a barrier/landing capture the opponent already ended her
    # own match on) -- the match is ending this round regardless, so the
    # scent snapshot no longer matters; carry the last known one forward
    # rather than crashing on None.get(...).
    next_scent = their_reveal.get("scent_grid", {}) if their_reveal is not None else last_opponent_scent
    turn_fsm.transition("WAITING_FOR_OPPONENT")
    return record, next_scent, False, None
