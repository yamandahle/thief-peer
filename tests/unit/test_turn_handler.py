"""TurnHandler tests (TODO_3 v0, rewired in Stage 4/TODO_4 to the real
BeliefGrid). Each turn: diffuse (the opponent moved somewhere since last
observation) then observe_scent (fold in what they just reported), then let
the brain decide against the real, full probability distribution -- no
Stage-3 ScriptedBelief shortcut remains in the move path (PRD_4 §2.4, §5)."""

from thief_peer.constants import MoveType
from thief_peer.domain.belief import BeliefGrid
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.peer.turn_handler import TurnHandler, run_scripted_match
from thief_peer.strategy.fleeing_brain import ThiefBrain


def test_turn_handler_owns_a_real_belief_grid():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    handler = TurnHandler(board, state, ThiefBrain())

    assert isinstance(handler.belief, BeliefGrid)


def test_turn_handler_play_turn_moves_the_state_and_returns_a_decision():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    handler = TurnHandler(board, state, ThiefBrain())

    decision = handler.play_turn(opponent_scent_snapshot={"0,0": 0.9})

    assert decision.move_type in (MoveType.MOVE, MoveType.HOLD)
    if decision.move_type == MoveType.MOVE:
        assert state.position != (2, 2)
        assert state.step_count == 1


def test_play_turn_folds_the_scent_snapshot_into_the_belief_grid():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    handler = TurnHandler(board, state, ThiefBrain())

    handler.play_turn(opponent_scent_snapshot={"6,6": 0.9, "6,5": 0.62, "5,6": 0.62})

    # belief should now lean toward the reported (scent-supported) region
    likely = handler.belief.most_likely()
    assert likely[0] >= 4 and likely[1] >= 4


def test_play_turn_folds_a_directional_hint_into_the_belief_grid():
    # book Ch.6.4 (page 47): the incoming hint text, not just scent, must
    # reach the belief update.
    board = Board(size=8, barriers=set())
    state = OwnGameState(position=(0, 0))
    handler = TurnHandler(board, state, ThiefBrain())

    handler.play_turn(opponent_scent_snapshot={}, opponent_hint_text="last seen out west")

    likely = handler.belief.most_likely()
    assert likely[1] < 4  # west half of the columns


def test_play_turn_defaults_to_no_hint_text():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    handler = TurnHandler(board, state, ThiefBrain())

    decision = handler.play_turn(opponent_scent_snapshot={"0,0": 0.9})  # no third arg

    assert decision.move_type in (MoveType.MOVE, MoveType.HOLD)


def test_run_scripted_match_plays_one_turn_per_scripted_scent_snapshot():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    scent_feed = [{"0,0": 0.9}, {"0,1": 0.62}, {"0,2": 0.42}]

    decisions = run_scripted_match(board, state, ThiefBrain(), scent_feed)

    assert len(decisions) == 3
    assert state.step_count == 3
