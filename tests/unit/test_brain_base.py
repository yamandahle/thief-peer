"""BrainBase/Decision/resolve_brain tests (PRD_3 §3, §5). `decide()` must
compute the move via `_pick_move` in pure Python before anything else touches
the Decision -- no LLM object ever appears in this path (structural check,
not just a runtime one: the relevant methods simply don't accept one)."""

import inspect

import pytest

from thief_peer.constants import MoveType
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.strategy.brain_base import BrainBase, Decision, resolve_brain
from thief_peer.strategy.fleeing_brain import ThiefBrain


class _FixedBrain(BrainBase):
    """Minimal concrete BrainBase for testing decide()'s own plumbing in
    isolation from ThiefBrain's actual scoring logic."""

    def _pick_move(self, moves, state, belief, board, own_scent):
        return moves[0]


class _NotABrain:
    pass


class _FixedBelief:
    def __init__(self, target, size):
        self._target = target
        self._size = size

    def as_matrix(self):
        matrix = [[0.0] * self._size for _ in range(self._size)]
        r, c = self._target
        matrix[r][c] = 1.0
        return matrix

    def most_likely(self):
        return self._target


def test_decide_returns_move_type_move_for_a_direction():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    belief = _FixedBelief((0, 0), 5)
    decision = _FixedBrain().decide(state, board, belief)
    assert isinstance(decision, Decision)
    # moves[0] from board.legal_moves((2,2), ...) is the first orthogonal
    # neighbor (N), not STAY -- so decide() must report MOVE, not HOLD.
    assert decision.move_type == MoveType.MOVE
    assert decision.direction is not None


def test_decide_defaults_verdict_to_truth_when_the_brain_does_not_override_it():
    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    belief = _FixedBelief((0, 0), 5)

    decision = _FixedBrain().decide(state, board, belief)

    assert decision.verdict == "truth"


def test_decide_uses_the_brains_own_choose_verdict_override():
    class _AlwaysLies(BrainBase):
        def _pick_move(self, moves, state, belief, board, own_scent):
            return moves[0]

        def _choose_verdict(self, cell, belief, board):
            return "lie"

    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    belief = _FixedBelief((0, 0), 5)

    decision = _AlwaysLies().decide(state, board, belief)

    assert decision.verdict == "lie"


def test_decide_returns_move_type_hold_when_pick_move_chooses_stay():
    class _AlwaysStay(BrainBase):
        def _pick_move(self, moves, state, belief, board, own_scent):
            return next((d, c) for d, c in moves if d is None)

    board = Board(size=5, barriers=set())
    state = OwnGameState(position=(2, 2))
    belief = _FixedBelief((0, 0), 5)
    decision = _AlwaysStay().decide(state, board, belief)
    assert decision.move_type == MoveType.HOLD
    assert decision.direction is None


def test_pick_move_and_helpers_have_no_llm_parameter():
    # Structural guarantee (PRD_3 §5): the LLM can never influence the move
    # because these signatures have no slot for one at all.
    for cls in (ThiefBrain,):
        for name in ("_pick_move", "_mobility_score", "_expected_distance", "_lookahead_score"):
            method = getattr(cls, name)
            params = inspect.signature(method).parameters
            assert "llm" not in params
            assert "provider" not in params


def test_resolve_brain_defaults_to_thief_brain_when_unset(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text("[network]\nmy_port = 8802\n", encoding="utf-8")
    from thief_peer.shared.config import ConfigManager

    config = ConfigManager(toml_path)
    brain = resolve_brain(config)
    assert isinstance(brain, ThiefBrain)


def test_resolve_brain_loads_a_configured_dotted_path(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[strategy]\nthief_class = "test_brain_base:_FixedBrain"\n',
        encoding="utf-8",
    )
    from thief_peer.shared.config import ConfigManager

    config = ConfigManager(toml_path)
    brain = resolve_brain(config)
    assert isinstance(brain, _FixedBrain)


def test_resolve_brain_fails_fast_on_malformed_selector(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[strategy]\nthief_class = "not-a-valid-selector"\n', encoding="utf-8"
    )
    from thief_peer.shared.config import ConfigManager

    config = ConfigManager(toml_path)
    with pytest.raises(TypeError):
        resolve_brain(config)


def test_resolve_brain_fails_fast_on_non_brainbase_target(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[strategy]\nthief_class = "test_brain_base:_NotABrain"\n',
        encoding="utf-8",
    )
    from thief_peer.shared.config import ConfigManager

    config = ConfigManager(toml_path)
    with pytest.raises(TypeError):
        resolve_brain(config)
