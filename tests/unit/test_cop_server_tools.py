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
from thief_peer.interop.cop_server_tools import CopContextAdapter, register_cop_tools
from thief_peer.interop.cop_turn_sender import (
    cop_request_scent_map,
    cop_send_barrier_declaration,
    cop_send_commit,
    cop_send_reveal,
)


class _SpyContext:
    def __init__(self):
        self.calls = []
        self.config = "cfg"
        self.group_name = "Thief-Team"
        self.repos = {"cop": "x", "thief": "y"}

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


def test_handle_receive_capture_claim_only_acknowledges():
    adapter = CopContextAdapter(_SpyContext(), shared_config_path="unused")
    assert adapter.handle_receive_capture_claim(1, 2, 3, 4, 9) == {"acknowledged": True}


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
