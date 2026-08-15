"""play_round_cop: one full commit/reveal round against a real Cop peer.
Mirrors `peer/round_loop.py::play_round`'s structure, but her round shape
genuinely differs: `receive_reveal` carries only move+hint (no inline
scent_grid); scent is a separate, explicitly-pulled channel
(`share_scent_map`), and her own `take_turn` pulls it *before* deciding,
not after revealing -- this function follows the same order.

Used to deliberately skip waiting on this side's own `round_exchange` for
her per-step reveal, on the theory that coupling two independently-paced
call sequences was a guarantee this scope boundary didn't need. A real
live match proved that wrong: her own event log showed her still honestly
mid-round-25 (hadn't even called her own `revealed` yet) when this side's
`receive_final_reveal` call landed on her, because this side's loop had
already raced ahead to its own local `max_moves` (35) without ever
checking her progress. That produced a real, cryptographically-honest-on-
both-sides step-count mismatch (35 vs. 25) every match, which her
orchestrator correctly refused to accept -- an automatic technical-
loss/tie under rule 35, every single run, not a race condition (the
disputed capture claims recur at the exact same steps every time --
deterministic strategies, not timing noise). Now mirrors native
`play_round`'s existing `wait_for_reveal` lockstep gate instead: blocks on
`round_exchange.wait_for_reveal(step, round_deadline_sec)` between
`AWAITING_REVEAL` and `VERIFYING` -- both edges already legal in
`turn_fsm.py`'s transition table -- so a stuck or slow peer now produces a
clean `TECHNICAL_LOSS` at the actual step in question (the Deadline
Tracker's real job, book Ch.8.4.1) instead of this side silently lapping
her.

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
from thief_peer.peer.strategy_deadline import run_with_deadline


def play_round_cop(
    step: int,
    turn_handler,
    turn_fsm,
    scent,
    trash_talk,
    round_exchange,
    transport,
    round_deadline_sec: float,
    strategy_deadline_sec: float,
    last_opponent_scent: dict,
) -> tuple[dict, dict, bool]:
    """Returns (sealed_record, next_opponent_scent, technical_loss)."""
    turn_fsm.transition("COMPUTING_MOVE")
    try:
        peer_scent = cop_request_scent_map(transport)
    except (DeadlineExceededError, TransportError):
        peer_scent = last_opponent_scent

    def _compute_move():
        decision = turn_handler.play_turn(peer_scent)
        decision.hint = trash_talk.generate_hint(step)
        return decision

    # Not caught here, same reasoning as native play_round: no sealed
    # record exists yet to return on a strategy-computation timeout -- let
    # it propagate to PeerRuntime.run()'s outer wrapper.
    decision = run_with_deadline(_compute_move, strategy_deadline_sec)
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
    try:
        round_exchange.wait_for_reveal(step, round_deadline_sec)
    except DeadlineExceededError:
        turn_fsm.transition("TECHNICAL_LOSS")
        return record, peer_scent, True

    turn_fsm.transition("VERIFYING")
    turn_fsm.transition("WAITING_FOR_OPPONENT")
    return record, peer_scent, False
