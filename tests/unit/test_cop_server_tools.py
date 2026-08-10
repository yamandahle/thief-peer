"""interop/cop_server_tools.py tests: CopContextAdapter translates her real
wire calls into this repo's existing context.handle_* methods -- proven
against a spy context (unit level) and, for the tool-registration wiring
itself, a real live FastMCP round trip using this repo's own outbound
cop_turn_sender functions as the caller (both halves of this repo's own
adapter talking to each other over real sockets, not a real Cop process,
but real proof the FastMCP wiring/shapes are actually correct)."""

import threading

import pytest
from fastmcp import FastMCP

from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.server_lifecycle import wait_until_ready
from thief_peer.interop.cop_server_registration import register_cop_tools
from thief_peer.interop.cop_server_tools import CopContextAdapter
from thief_peer.interop.cop_turn_sender import (
    cop_request_scent_map,
    cop_send_barrier_declaration,
    cop_send_commit,
    cop_send_final_reveal,
    cop_send_reveal,
)


class _State:
    def __init__(self, position=(0, 0)):
        self.position = position  # (row, col), matching domain/board.py's Cell


class _FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, name, payload):
        self.calls.append((name, payload))
        return {"acknowledged": True}


class _Cfg:
    def require(self, key):
        return {
            "board_and_agents.cop_start": [0, 0],
            "board_and_agents.grid_size": 7,
        }[key]


class _SpyContext:
    def __init__(self, position=(0, 0)):
        self.calls = []
        self.config = _Cfg()
        self.group_name = "Thief-Team"
        self.repos = {"cop": "x", "thief": "y"}
        self.state = _State(position)
        self.transport = _FakeTransport()

        class _Scent:
            def snapshot(self):
                return {"4,3": 0.62}

        self.scent = _Scent()

    def handle_commit_move(self, payload):
        self.calls.append(("commit_move", payload))
        return {"ok": True}

    def handle_reveal_move(self, payload):
        self.calls.append(("reveal_move", payload))
        return {"ok": True}

    def handle_receive_barrier_declaration(self, payload):
        self.calls.append(("receive_barrier_declaration", payload))
        return {"ok": True}


def test_handle_receive_commit_assigns_sequential_steps_and_delegates():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_commit("hash-0")
    adapter.handle_receive_commit("hash-1")

    assert context.calls == [
        ("commit_move", {"step": 0, "h_commit": "hash-0"}),
        ("commit_move", {"step": 1, "h_commit": "hash-1"}),
    ]


def test_handle_receive_reveal_translates_her_typed_move_into_our_direction_string():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    result = adapter.handle_receive_reveal({"type": "move", "direction": "N"}, "cold")

    assert context.calls == [
        ("reveal_move", {"step": 0, "sender": "cop", "hint": "cold", "scent_grid": {}, "move": "N", "intent": "truth"})
    ]
    assert result == {"accepted": True, "word_count": 1}


def test_handle_share_scent_map_serializes_the_live_scent_field():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    assert adapter.handle_share_scent_map() == {"cells": [[3, 4, 0.62]]}


def test_handle_receive_barrier_declaration_swaps_col_row_into_our_row_col_payload():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_barrier_declaration(col=5, row=2)

    assert context.calls == [("receive_barrier_declaration", {"row": 2, "col": 5})]


def test_handle_receive_barrier_declaration_acks_in_her_shape_not_the_native_one():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    result = adapter.handle_receive_barrier_declaration(col=5, row=2)

    assert result == {"acknowledged": True}


def test_handle_receive_capture_claim_acks_immediately_then_confirms_a_real_capture():
    context = _SpyContext(position=(2, 5))  # actually standing at row=2, col=5
    adapter = CopContextAdapter(context, shared_config_path="unused")

    result = adapter.handle_receive_capture_claim(
        thief_col=5, thief_row=2, cop_col=5, cop_row=2, claimed_at_step=9
    )

    assert result == {"acknowledged": True}
    adapter._capture_response_thread.join(timeout=1)
    assert context.transport.calls == [
        ("receive_capture_response", {"confirmed": True, "true_thief_col": 5, "true_thief_row": 2})
    ]


def test_handle_receive_capture_claim_denies_and_reveals_true_position_when_wrong():
    context = _SpyContext(position=(9, 9))  # actually standing elsewhere
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_capture_claim(
        thief_col=5, thief_row=2, cop_col=5, cop_row=2, claimed_at_step=9
    )

    adapter._capture_response_thread.join(timeout=1)
    assert context.transport.calls == [
        ("receive_capture_response", {"confirmed": False, "true_thief_col": 9, "true_thief_row": 9})
    ]


def test_handle_receive_final_reveal_audits_peer_and_acks():
    # Ch.5.3.2 + rules 19/36: Final Reveal triggers peer audit, not ack-only.
    adapter = CopContextAdapter(_SpyContext(position=(2, 5)), shared_config_path="unused")
    adapter.peer_trace.record_commit("deadbeef")
    adapter.peer_trace.record_reveal({"type": "move", "direction": "E"}, "hint")

    result = adapter.handle_receive_final_reveal({"1": "n" * 32}, {"1": True})

    assert result["acknowledged"] is True
    assert "passed" in result
    assert adapter.final_reveal_received.is_set()
    assert adapter.opponent_audit["evaluated"] is True


def test_handle_receive_final_reveal_acks_when_empty():
    adapter = CopContextAdapter(_SpyContext(), shared_config_path="unused")
    assert adapter.handle_receive_final_reveal({}, {})["acknowledged"] is True



@pytest.fixture
def live_server_with_cop_adapter(free_tcp_port):
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")
    mcp = FastMCP(name="thief-peer-cop-adapter")
    register_cop_tools(mcp, adapter)
    thread = threading.Thread(
        target=mcp.run,
        kwargs={
            "transport": "http",
            "host": "127.0.0.1",
            "port": free_tcp_port,
            "show_banner": False,
            "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    wait_until_ready(free_tcp_port)
    yield free_tcp_port, context


def test_cop_send_commit_and_cop_send_reveal_actually_land_on_the_registered_server(
    live_server_with_cop_adapter,
):
    port, context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    cop_send_commit(transport, "hash-0")
    cop_send_reveal(transport, "N", "cold")

    assert context.calls == [
        ("commit_move", {"step": 0, "h_commit": "hash-0"}),
        ("reveal_move", {"step": 0, "sender": "cop", "hint": "cold", "scent_grid": {}, "move": "N", "intent": "truth"}),
    ]


def test_cop_request_scent_map_round_trips_over_a_real_socket(live_server_with_cop_adapter):
    port, _context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = cop_request_scent_map(transport)

    assert result == {"4,3": 0.62}


def test_cop_send_barrier_declaration_lands_with_row_col_swapped_back(live_server_with_cop_adapter):
    port, context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    cop_send_barrier_declaration(transport, row=2, col=5)

    assert context.calls == [("receive_barrier_declaration", {"row": 2, "col": 5})]


def test_cop_send_final_reveal_lands_on_the_registered_server(live_server_with_cop_adapter):
    port, _context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = cop_send_final_reveal(transport, {"0": "nonce"}, {"0": True})

    assert result["acknowledged"] is True
    assert "passed" in result  # rules 19/36 audit summary rides on the ack

