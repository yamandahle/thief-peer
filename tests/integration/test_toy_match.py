"""Stage 3 integration test (TODO_3, updated Stage 4/TODO_4): wires
ThiefBrain into the Stage-2 MCP loop for a toy two-localhost-peer match. A
real server plays the "opponent" role, serving a scripted feed of scent
snapshots (Stage 4's real wire content, replacing Stage 3's raw-position
feed) through the same `ping` tool Stage 2 established as its stand-in
transport (the real `receive_turn` tool arrives Stage 6); a real
McpTransport client fetches each round's snapshot and feeds it to
TurnHandler, which drives a real ThiefBrain decision against a real
BeliefGrid and applies it to state -- proving the pure-Python move logic
and the P2P transport compose end to end, not just in isolation.
"""

import socket
import threading

import pytest

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.scent import ScentField
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import NullPeerContext, build_server, wait_until_ready
from thief_peer.peer.turn_handler import TurnHandler
from thief_peer.strategy.fleeing_brain import ThiefBrain

SCRIPTED_COP_TRAIL = [(0, 0), (0, 1), (1, 1), (1, 2)]


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


def test_thief_brain_drives_moves_from_a_real_mcp_scripted_scent_feed(opponent_feed_server):
    transport = McpTransport(f"http://127.0.0.1:{opponent_feed_server}/mcp")
    board = Board(size=9, barriers=set())
    state = OwnGameState(position=(4, 4))
    handler = TurnHandler(board, state, ThiefBrain())
    cop_scent = ScentField(board_size=9)

    decisions = []
    for cop_position in SCRIPTED_COP_TRAIL:
        # The scripted "Cop" emits real scent as it moves, exactly as the
        # book's formula requires (PRD_4 §2.1) -- not a raw position leak.
        cop_scent.advance(cop_position)
        # Real MCP round trip carries the resulting snapshot -- the
        # opponent's server just echoes it back, standing in for the real
        # Cop process's outgoing TurnMessage.scent_grid.
        echoed = transport.call("ping", {"payload": {"scent_grid": cop_scent.snapshot()}})
        fed_snapshot = echoed["received"]["scent_grid"]
        decisions.append(handler.play_turn(fed_snapshot))

    assert len(decisions) == len(SCRIPTED_COP_TRAIL)
    assert state.step_count == len(SCRIPTED_COP_TRAIL)
