"""interop/std_v1/server_registration.py tests -- a real live server, real
socket round trip, matching test_cop_server_tools.py's own established
pattern for the identical kind of check."""

import threading

import pytest
from fastmcp import FastMCP

from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.server_lifecycle import wait_until_ready
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.server_registration import register_std_v1_tools


@pytest.fixture
def live_server_with_exchange(free_tcp_port):
    exchange = StdExchange(poll_interval=0.01)
    mcp = FastMCP(name="thief-peer-std-v1")
    register_std_v1_tools(mcp, exchange)
    thread = threading.Thread(
        target=mcp.run,
        kwargs={
            "transport": "http", "host": "127.0.0.1", "port": free_tcp_port,
            "show_banner": False, "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    wait_until_ready(free_tcp_port)
    yield free_tcp_port, exchange


def test_negotiate_lands_on_the_exchange(live_server_with_exchange):
    port, exchange = live_server_with_exchange
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = transport.call("negotiate", {"message": {"sub_game_number": 1, "group_id": "g"}})

    assert result == {"ok": True}
    assert exchange.wait_for_offer(1, timeout=2.0)["group_id"] == "g"


def test_receive_turn_lands_on_the_exchange(live_server_with_exchange):
    port, exchange = live_server_with_exchange
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    transport.call("receive_turn", {"message": {"step": 3, "sender": "police"}})

    assert exchange.wait_for_turn(3, timeout=2.0)["sender"] == "police"


def test_submit_audit_lands_on_the_exchange_not_the_native_handler(live_server_with_exchange):
    port, exchange = live_server_with_exchange
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    transport.call(
        "submit_audit",
        {"payload": {"sub_game_number": 2, "result_claim": "capture", "sender": "thief", "records": []}},
    )

    assert exchange.wait_for_audit(2, timeout=2.0)["result_claim"] == "capture"


def test_receive_control_lands_on_the_exchange(live_server_with_exchange):
    port, exchange = live_server_with_exchange
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    transport.call("receive_control", {"message": {"type": "ping"}})

    assert exchange.latest_control() == {"type": "ping"}
