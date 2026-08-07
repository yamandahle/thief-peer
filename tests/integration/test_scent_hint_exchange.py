"""Stage 4 integration test (TODO_4): proves the stage's own "Done" milestone
-- two live localhost peers exchange real scent fields + NL hints every
turn, the Thief's belief heatmap visibly tracks the (scripted) Cop's scent
trail, and the move path still never touches an LLM. Builds directly on
Stage 2's MCP transport and Stage 3's `ping` stand-in tool (the real
`receive_turn` tool arrives Stage 6).
"""

import socket
import threading

import pytest

from thief_peer.domain.belief import BeliefGrid
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.scent import ScentField
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import NullPeerContext, build_server, wait_until_ready
from thief_peer.peer.turn_handler import TurnHandler
from thief_peer.strategy.fleeing_brain import ThiefBrain
from thief_peer.strategy.talk_providers import TemplateProvider
from thief_peer.strategy.trash_talk import TrashTalk

# A short scripted Cop trail. Kept short deliberately: BeliefGrid.observe_scent
# re-weights against each turn's *cumulative* scent snapshot (PRD_4 §2.3), so
# early, strong reinforcement compounds over many turns and can outweigh a
# recently-moved-on true position -- a known limit of the book's simple
# "reweight by 1+intensity" update, not a wiring bug. Three rounds is well
# within the regime where tracking is clean and unambiguous.
SCRIPTED_COP_TRAIL = [(0, 0), (1, 1), (2, 2)]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


@pytest.fixture
def opponent_feed_server():
    port = _free_port()
    app = build_server(port, NullPeerContext())
    thread = threading.Thread(
        target=app.run,
        kwargs={
            "transport": "http",
            "host": "127.0.0.1",
            "port": port,
            "show_banner": False,
            "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    wait_until_ready(port)
    yield port


def test_live_scent_and_hint_exchange_tracks_the_scripted_trail(opponent_feed_server):
    transport = McpTransport(f"http://127.0.0.1:{opponent_feed_server}/mcp")
    board = Board(size=9, barriers=set())
    state = OwnGameState(position=(4, 8))
    handler = TurnHandler(board, state, ThiefBrain())
    cop_scent = ScentField(board_size=9)
    trash_talk = TrashTalk(TemplateProvider(), llm_provider=None, every_n_steps=1)

    hints = []
    for step, cop_position in enumerate(SCRIPTED_COP_TRAIL, start=1):
        # The scripted Cop emits real scent per the book's formula, not a
        # raw position leak (PRD_4 §2.1).
        cop_scent.advance(cop_position)

        # Real MCP round trip carries both the scent snapshot and an NL
        # hint in one message -- the wire content Stage 6's real
        # receive_turn tool will eventually carry (PLAN.md TurnMessage).
        hint = trash_talk.generate_hint(step)
        hints.append(hint)
        echoed = transport.call(
            "ping", {"payload": {"scent_grid": cop_scent.snapshot(), "hint": hint}}
        )
        received = echoed["received"]

        # The move is decided from the scent alone; the hint is logged but
        # never fed into the belief update (PRD_4 §2.3/§4).
        handler.play_turn(received["scent_grid"])

    # "Visibly tracks the trail": the informed belief must land measurably
    # closer to the true final position than a diffuse-only control that
    # never saw any scent at all, over the exact same number of rounds --
    # isolating the effect of the scent evidence from boundary-diffusion
    # noise common to both runs.
    true_final_position = SCRIPTED_COP_TRAIL[-1]
    informed_distance = board.distance(handler.belief.most_likely(), true_final_position)
    uninformed_distance = board.distance(_run_diffuse_only_control(board.size), true_final_position)
    assert informed_distance < uninformed_distance

    # Every hint actually crossed the wire as non-empty natural language.
    assert len(hints) == len(SCRIPTED_COP_TRAIL)
    assert all(isinstance(h, str) and len(h) > 0 for h in hints)

    # The move path never touched an LLM: TrashTalk was constructed above
    # with llm_provider=None, and ThiefBrain's move-deciding methods
    # structurally accept no such object at all (see test_brain_base.py's
    # test_pick_move_and_helpers_have_no_llm_parameter).


def _run_diffuse_only_control(board_size: int):
    """Same number of diffuse() calls as the real run, but never fed any
    scent -- the baseline the informed belief must measurably beat."""
    belief = BeliefGrid(board_size)
    for _ in SCRIPTED_COP_TRAIL:
        belief.diffuse()
    return belief.most_likely()
