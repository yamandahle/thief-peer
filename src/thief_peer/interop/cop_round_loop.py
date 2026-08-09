"""play_round_cop: one full commit/reveal round against a real Cop peer.
Mirrors `peer/round_loop.py::play_round`'s structure, but her round shape
genuinely differs: `receive_reveal` carries only move+hint (no inline
scent_grid); scent is a separate, explicitly-pulled channel
(`share_scent_map`), and her own `take_turn` pulls it *before* deciding,
not after revealing -- this function follows the same order.

Deliberately does not block on this side's own `round_exchange` to learn
her per-step reveal (unlike native `play_round`'s `wait_for_reveal`): doing
so would require this side's inbound `CopContextAdapter`'s own step
counter to stay lock-step with this loop's `step` numbering, coupling two
independently-paced call sequences for a guarantee this scope boundary
doesn't need. A `share_scent_map` pull that lands slightly before or after
her own current move is the same kind of approximate, time-decayed signal
scent already is everywhere else in this game -- not a new class of risk
this loop needs to close.

`state`/`move`/`intent` here are built via `interop/cop_wire.py`'s
`build_cop_state_string`/`build_cop_move_envelope` and a booleanized
`decision.verdict`, not this side's own internal shapes -- required for
her real end-of-match audit to recompute the identical `Hcommit` this side
sealed (see `interop/__init__.py` and `tests/unit/test_cop_wire.py`'s
cross-repo check), not just a wire-compatible-looking gesture.
"""

from thief_peer.exceptions import DeadlineExceededError, TransportError
from thief_peer.interop.cop_turn_sender import (
    cop_request_scent_map,
    cop_send_commit,
    cop_send_reveal,
)
from thief_peer.interop.cop_wire import build_cop_move_envelope, build_cop_state_string
from thief_peer.peer.sealing import sealed_step_record


def play_round_cop(
    step: int,
    turn_handler,
    turn_fsm,
    scent,
    trash_talk,
    transport,
    last_opponent_scent: dict,
) -> tuple[dict, dict, bool]:
    """Returns (sealed_record, next_opponent_scent, technical_loss)."""
    turn_fsm.transition("COMPUTING_MOVE")
    try:
        peer_scent = cop_request_scent_map(transport)
    except (DeadlineExceededError, TransportError):
        peer_scent = last_opponent_scent

    decision = turn_handler.play_turn(peer_scent)
    decision.hint = trash_talk.generate_hint(step)
    scent.advance(turn_handler.state.position)

    move = decision.direction.value if decision.direction else "STAY"
    my_row, my_col = turn_handler.state.position
    record = sealed_step_record(
        state=build_cop_state_string(my_row, my_col, turn_handler.state.step_count),
        move=build_cop_move_envelope(move),
        intent=decision.verdict == "truth",
        hint_text=decision.hint,
        step=step,
        role="thief",
    )

    turn_fsm.transition("COMMITTING")
    try:
        cop_send_commit(transport, record["commit"])
        cop_send_reveal(transport, move, decision.hint)
    except (DeadlineExceededError, TransportError):
        # The book's own transition table (also respected by native
        # play_round) has no direct COMMITTING -> TECHNICAL_LOSS edge --
        # only AWAITING_REVEAL -> TECHNICAL_LOSS. Found by an actual
        # mid-match connection drop during a real live run, not by
        # inspection: skipping this intermediate step raised a
        # SimulationError instead of cleanly recording the technical loss.
        turn_fsm.transition("AWAITING_REVEAL")
        turn_fsm.transition("TECHNICAL_LOSS")
        return record, peer_scent, True

    turn_fsm.transition("AWAITING_REVEAL")
    turn_fsm.transition("VERIFYING")
    turn_fsm.transition("WAITING_FOR_OPPONENT")
    return record, peer_scent, False
