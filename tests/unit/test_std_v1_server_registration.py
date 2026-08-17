"""interop/std_v1/server_registration.py tests: three of the four std_v1
tool names collide with the native protocol's own tools -- an std_v1
server must always answer the spec's own shape for those three, never
silently keep the native handler underneath."""

import asyncio

from fastmcp import FastMCP

from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.server_registration import register_std_v1_tools


def _call(mcp: FastMCP, name: str, arguments: dict) -> dict:
    result = asyncio.run(mcp.call_tool(name, arguments))
    return result.structured_content


def test_register_std_v1_tools_replaces_a_colliding_native_tool():
    mcp = FastMCP("x")
    native_calls = []

    @mcp.tool
    def negotiate(terms, nonce, commit) -> dict:  # native protocol's own shape
        native_calls.append((terms, nonce, commit))
        return {"native": True}

    exchange = StdExchange()
    register_std_v1_tools(mcp, exchange)

    result = _call(mcp, "negotiate", {"message": {"group_id": "peer"}})
    assert result == {"ok": True}
    assert native_calls == []  # the native handler must be gone, not just shadowed


def test_register_std_v1_tools_works_when_no_native_tool_exists_to_collide_with():
    mcp = FastMCP("x")
    exchange = StdExchange()
    register_std_v1_tools(mcp, exchange)  # must not raise despite nothing to remove


def test_negotiate_tool_records_the_offer_onto_the_exchange():
    mcp = FastMCP("x")
    exchange = StdExchange(poll_interval=0.01)
    register_std_v1_tools(mcp, exchange)

    _call(mcp, "negotiate", {"message": {"sub_game_number": 1, "group_id": "peer"}})

    assert exchange.wait_for_offer(1, timeout=0.1) == {"sub_game_number": 1, "group_id": "peer"}


def test_receive_turn_tool_records_the_turn_onto_the_exchange():
    mcp = FastMCP("x")
    exchange = StdExchange(poll_interval=0.01)
    register_std_v1_tools(mcp, exchange)

    _call(mcp, "receive_turn", {"message": {"step": 1, "move": "N"}})

    assert exchange.wait_for_turn(1, timeout=0.1) == {"step": 1, "move": "N"}


def test_submit_audit_and_receive_control_tools_reach_the_exchange():
    mcp = FastMCP("x")
    exchange = StdExchange(poll_interval=0.01)
    register_std_v1_tools(mcp, exchange)

    _call(mcp, "submit_audit", {"payload": {"sub_game_number": 1, "result_claim": "capture", "records": []}})
    _call(mcp, "receive_control", {"message": {"type": "pause"}})

    assert exchange.wait_for_audit(1, timeout=0.1) == {
        "sub_game_number": 1, "result_claim": "capture", "records": [],
    }
    assert exchange.latest_control() == {"type": "pause"}
