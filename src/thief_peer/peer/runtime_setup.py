"""build_game_components (PRD_8 §3): constructs the pure-gameplay pieces
(board/state/brain/belief/scent/trash-talk) a PeerRuntime needs from
`ConfigManager`, reading every value through `CANONICAL_TERM_KEYS` so the
wire vocabulary and the local config lookup never drift apart (`PLAN.md`
ADR-6). Extracted out of `peer/runtime.py` to keep that file under this
codebase's file-length convention.
"""

from types import SimpleNamespace

from thief_peer.domain.board import Board
from thief_peer.domain.negotiation import CANONICAL_TERM_KEYS
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.scent import ScentField
from thief_peer.peer.turn_handler import TurnHandler
from thief_peer.strategy.brain_base import resolve_brain
from thief_peer.strategy.talk_providers import TemplateProvider
from thief_peer.strategy.trash_talk import TrashTalk


def build_game_components(config, gatekeeper=None) -> SimpleNamespace:
    def _term(wire_key: str):
        return config.require(CANONICAL_TERM_KEYS[wire_key])

    board = Board(size=_term("grid_size"), barriers=set())
    state = OwnGameState(position=tuple(_term("thief_start")))
    turn_handler = TurnHandler(board, state, resolve_brain(config))
    scent = ScentField(
        board_size=_term("grid_size"),
        center_intensity=_term("scent_center_intensity"),
        decay_rate=_term("scent_decay_rate"),
    )
    trash_talk = TrashTalk(
        TemplateProvider(),
        llm_provider=None,
        hint_max_words=_term("hint_word_limit"),
        map_area=config.get("world.map_area", ""),
        gatekeeper=gatekeeper,
    )
    return SimpleNamespace(
        board=board,
        state=state,
        turn_handler=turn_handler,
        scent=scent,
        trash_talk=trash_talk,
        survival_threshold=_term("survival_threshold"),
        max_moves=_term("max_moves"),
    )
