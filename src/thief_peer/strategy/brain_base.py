"""Strategy boundary (PLAN.md ADR-1, ADR-7; PRD_3 Ch.6). `BrainBase.decide()`
always computes the move via `_pick_move` in pure Python first -- the move
half of `Decision` has no code path that touches an LLM. `hint`/`verdict`/
`reasoning` are filled in by Stage 4's trash-talk layer, never here.
"""

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

from thief_peer.constants import Direction, MoveType
from thief_peer.domain.board import Board, Cell
from thief_peer.domain.own_state import OwnGameState
from thief_peer.shared.config import ConfigManager


@dataclass
class Decision:
    """Strategy -> peer boundary (PLAN.md §5), Thief-repo only, never sent
    on the wire as-is. Thief never produces `move_type == BARRIER`."""

    move_type: MoveType
    direction: Direction | None
    hint: str = ""
    verdict: str = "truth"
    reasoning: str = ""
    response_seconds: float = 0.0


class BrainBase(ABC):
    def decide(
        self,
        state: OwnGameState,
        board: Board,
        belief,
        opponent_hint: str = "",
    ) -> Decision:
        # opponent_hint is unused until Stage 4's trash-talk verdict bias
        # (PRD_3 §3) -- kept in the signature now so it isn't a breaking
        # change to add later.
        moves = board.legal_moves(state.position, frozenset(state.known_barriers))
        direction, _cell = self._pick_move(moves, state, belief, board)
        move_type = MoveType.MOVE if direction is not None else MoveType.HOLD
        return Decision(move_type=move_type, direction=direction)

    @abstractmethod
    def _pick_move(
        self,
        moves: list[tuple[Direction | None, Cell]],
        state: OwnGameState,
        belief,
        board: Board,
    ) -> tuple[Direction | None, Cell]:
        """Subclasses implement the actual policy. Never accepts an LLM/
        provider object -- see PRD_3 §5's structural LLM-never-called
        guarantee."""


def resolve_brain(config: ConfigManager, llm=None, rng=None) -> BrainBase:
    """Dotted-path factory (PLAN.md ADR-7): `[strategy] thief_class =
    "pkg.module:ClassName"` in the private TOML, defaulting to the shipped
    `ThiefBrain`. `llm`/`rng` are accepted for pluggable brains that may want
    them later; the shipped `ThiefBrain` uses neither."""
    from thief_peer.strategy.fleeing_brain import ThiefBrain

    dotted_path = config.get("strategy.thief_class")
    if not dotted_path:
        return ThiefBrain()

    module_name, _, class_name = str(dotted_path).partition(":")
    if not module_name or not class_name:
        raise TypeError(
            f"Malformed strategy.thief_class selector: {dotted_path!r} "
            f"(expected 'module.path:ClassName')"
        )

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name, None)
    if not (isinstance(cls, type) and issubclass(cls, BrainBase)):
        raise TypeError(f"{dotted_path!r} does not name a BrainBase subclass")
    return cls()
