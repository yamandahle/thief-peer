"""TurnHandler v0 tests (TODO_3): applies a scripted incoming "cop position"
feed, single-process self-play. ScriptedBelief is this stage's stand-in for
domain/belief.py:BeliefGrid (arriving Stage 4) -- it exposes the same
as_matrix()/most_likely() interface ThiefBrain's scoring already targets."""

from thief_peer.constants import MoveType
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.peer.turn_handler import ScriptedBelief, TurnHandler, run_scripted_match
from thief_peer.strategy.fleeing_brain import ThiefBrain


def test_scripted_belief_puts_all_mass_on_the_target_cell():
    belief = ScriptedBelief(target=(2, 3), board_size=5)
    assert belief.most_likely() == (2, 3)
    matrix = belief.as_matrix()
    assert matrix[2][3] == 1.0
    assert sum(sum(row) for row in matrix) == 1.0


def test_turn_handler_play_turn_moves_the_state_and_returns_a_decision():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    handler = TurnHandler(board, state, ThiefBrain())

    decision = handler.play_turn(believed_cop_position=(0, 0))

    assert decision.move_type in (MoveType.MOVE, MoveType.HOLD)
    if decision.move_type == MoveType.MOVE:
        assert state.position != (2, 2)
        assert state.step_count == 1


def test_run_scripted_match_plays_one_turn_per_scripted_position():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    cop_positions = [(0, 0), (0, 1), (0, 2)]

    decisions = run_scripted_match(board, state, ThiefBrain(), cop_positions)

    assert len(decisions) == 3
    assert state.step_count == 3
