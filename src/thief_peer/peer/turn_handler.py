"""TurnHandler (TODO_3 v0, rewired Stage 4/TODO_4): drives one Thief turn
against a real belief grid updated from the opponent's scent snapshot --
diffuse (the opponent moved somewhere since the last observation), then
observe_scent (fold in what they just reported), then let the brain decide
against the full distribution. Replaces Stage 3's ScriptedBelief stand-in
entirely (PRD_4 §2.4: no most_likely()-only shortcut remains in the move
path). Stands in for the full turn protocol (negotiation, sealing, sending)
later stages add; this version only exercises state + belief + brain.
"""

from thief_peer.domain.belief import BeliefGrid
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.brain_base import BrainBase, Decision


class TurnHandler:
    def __init__(self, board: Board, state: OwnGameState, brain: BrainBase):
        self.board = board
        self.state = state
        self.brain = brain
        self.belief = BeliefGrid(board.size)

    def play_turn(
        self,
        opponent_scent_snapshot: dict[str, float],
        declared_position: tuple[int, int] | None = None,
        declared_radius: int = 0,
    ) -> Decision:
        """`declared_position` (PLAN.md Stage 7.4), if given, is the
        opponent's own stated cell -- its `capture_claim` (radius 0) or the
        cell orthogonally adjacent to a `barrier_placed` it declared
        (radius 1) -- folded in via `BeliefGrid.observe_declaration` as a
        second evidence channel, separate from scent."""
        self.belief.diffuse()
        self.belief.observe_scent(opponent_scent_snapshot)
        if declared_position is not None:
            self.belief.observe_declaration(declared_position, radius=declared_radius)
        decision = self.brain.decide(self.state, self.board, self.belief)
        self.state.apply_move(decision.direction, self.board)
        return decision


def run_scripted_match(
    board: Board,
    state: OwnGameState,
    brain: BrainBase,
    scent_feed: list[dict[str, float]],
) -> list[Decision]:
    handler = TurnHandler(board, state, brain)
    return [handler.play_turn(snapshot) for snapshot in scent_feed]
