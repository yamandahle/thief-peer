"""TurnHandler (TODO_3 v0, rewired Stage 4/TODO_4, hint-folding added book
Ch.6.4 page 47): drives one Thief turn against a real belief grid updated
from the opponent's scent snapshot and their incoming hint text -- diffuse
(the opponent moved somewhere since the last observation), then
observe_scent (fold in what they just reported, fully trusted), then
observe_hint (fold in a parsed direction cue from their hint text, weighted
by HINT_RELIABILITY since it may be false), then let the brain decide
against the full distribution. Replaces Stage 3's ScriptedBelief stand-in
entirely (PRD_4 §2.4: no most_likely()-only shortcut remains in the move
path). Stands in for the full turn protocol (negotiation, sealing, sending)
later stages add; this version only exercises state + belief + brain.
"""

from thief_peer.domain.belief import BeliefGrid
from thief_peer.domain.board import Board
from thief_peer.domain.hint_direction import parse_direction_cue
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.brain_base import HINT_RELIABILITY, BrainBase, Decision


class TurnHandler:
    def __init__(self, board: Board, state: OwnGameState, brain: BrainBase):
        self.board = board
        self.state = state
        self.brain = brain
        self.belief = BeliefGrid(board.size)

    def play_turn(
        self, opponent_scent_snapshot: dict[str, float], opponent_hint_text: str = ""
    ) -> Decision:
        self.belief.diffuse()
        self.belief.observe_scent(opponent_scent_snapshot)
        cue = parse_direction_cue(opponent_hint_text, self.board.size)
        self.belief.observe_hint(cue, HINT_RELIABILITY)
        decision = self.brain.decide(self.state, self.board, self.belief, opponent_hint_text)
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
