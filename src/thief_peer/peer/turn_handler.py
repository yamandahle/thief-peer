"""TurnHandler v0 (TODO_3): drives one Thief turn against a scripted feed of
believed Cop positions -- applies the chosen move to state and returns the
Decision. Stands in for the full turn protocol (negotiation, sealing,
sending) later stages add; this version only exercises state + brain.

`ScriptedBelief` is this stage's stand-in for the real `domain/belief.py:
BeliefGrid` arriving in Stage 4 -- it exposes the same `as_matrix()`/
`most_likely()` interface ThiefBrain's scoring already targets (PRD_3 scope
note), so no rework is needed once the real Bayesian belief grid lands.
"""

from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.brain_base import BrainBase, Decision


class ScriptedBelief:
    def __init__(self, target: Cell, board_size: int):
        self._target = target
        self._size = board_size

    def as_matrix(self) -> list[list[float]]:
        matrix = [[0.0] * self._size for _ in range(self._size)]
        r, c = self._target
        matrix[r][c] = 1.0
        return matrix

    def most_likely(self) -> Cell:
        return self._target


class TurnHandler:
    def __init__(self, board: Board, state: OwnGameState, brain: BrainBase):
        self.board = board
        self.state = state
        self.brain = brain

    def play_turn(self, believed_cop_position: Cell) -> Decision:
        belief = ScriptedBelief(believed_cop_position, self.board.size)
        decision = self.brain.decide(self.state, self.board, belief)
        self.state.apply_move(decision.direction, self.board)
        return decision


def run_scripted_match(
    board: Board, state: OwnGameState, brain: BrainBase, cop_positions: list[Cell]
) -> list[Decision]:
    handler = TurnHandler(board, state, brain)
    return [handler.play_turn(position) for position in cop_positions]
