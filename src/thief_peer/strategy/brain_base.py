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

# Book Ch.6.4 (page 47) requires folding hints into the belief update with
# "a reliability coefficient... since the text may be false," but gives no
# number -- kept low, well below scent's implicit full trust, so a false
# hint can never outweigh the unfakeable scent signal (same kind of
# unspecified-by-the-book constant as trash_talk.py's _LIE_THRESHOLD).
HINT_RELIABILITY = 0.3


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
        own_scent: dict[str, float] | None = None,
    ) -> Decision:
        # opponent_hint is unused until Stage 4's trash-talk verdict bias
        # (PRD_3 §3) -- kept in the signature now so it isn't a breaking
        # change to add later. own_scent (ch.1.4, p.6) is this side's own
        # sparse `{"r,c": intensity}` trail as of *before* this turn's move
        # -- `None` (no caller-supplied signal) is normalized to `{}` here,
        # once, so every `_pick_move` implementation can treat "no data" and
        # "genuinely empty trail" identically without its own null check.
        moves = board.legal_moves(state.position, frozenset(state.known_barriers))
        direction, cell = self._pick_move(moves, state, belief, board, own_scent or {})
        move_type = MoveType.MOVE if direction is not None else MoveType.HOLD
        verdict = self._choose_verdict(cell, belief, board)
        return Decision(move_type=move_type, direction=direction, verdict=verdict)

    @abstractmethod
    def _pick_move(
        self,
        moves: list[tuple[Direction | None, Cell]],
        state: OwnGameState,
        belief,
        board: Board,
        own_scent: dict[str, float],
    ) -> tuple[Direction | None, Cell]:
        """Subclasses implement the actual policy. Never accepts an LLM/
        provider object -- see PRD_3 §5's structural LLM-never-called
        guarantee."""

    def _choose_verdict(self, cell: Cell, belief, board: Board) -> str:
        """Book ch.6.5/1.4: whether this round's hint should be honest or a
        deliberate lie. Default always truthful -- a pluggable brain that
        doesn't model a real strategy here (PLAN.md ADR-7) shouldn't be
        forced to. `ThiefBrain` overrides this with the book's actual
        expected-distance-biased strategy (`strategy/trash_talk.py::
        choose_verdict`)."""
        return "truth"


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
