"""register_std_v1_tools: attaches the spec's four tools onto an
already-constructed FastMCP instance, matching interop/
cop_server_registration.py's own established pattern for the identical
underlying problem.

Three of the four names collide with the native protocol's own tools,
already registered by infra/mcp_server.py::build_server, but with
genuinely different argument shapes and handler behavior:
`negotiate(terms, nonce, commit, scent_lock_hash, config_sha256=None)`
vs. this spec's `negotiate(message)`; `receive_control(type, record)` vs.
`receive_control(message)`; and `submit_audit(payload)` -- same parameter
name and type as this spec's own, but wired to the native protocol's own
audit handler, not std_v1's, so it still needs replacing rather than
being trusted by coincidence. `mcp.tool` doesn't overwrite an existing
registration (only warns and keeps the first), so the native versions are
explicitly removed first -- an std_v1 server always answers the spec's
own shape for these three, never silently keeps the native one
underneath. `receive_turn` is new and never collides.
"""

from __future__ import annotations

import contextlib

from fastmcp import FastMCP

from thief_peer.interop.std_v1.exchange import StdExchange

_COLLIDES_WITH_NATIVE = ("negotiate", "submit_audit", "receive_control")


def register_std_v1_tools(mcp: FastMCP, exchange: StdExchange) -> None:
    for name in _COLLIDES_WITH_NATIVE:
        with contextlib.suppress(KeyError):
            mcp.local_provider.remove_tool(name)

    @mcp.tool
    def negotiate(message: dict) -> dict:
        exchange.record_offer(message)
        return {"ok": True}

    @mcp.tool
    def receive_turn(message: dict) -> dict:
        exchange.record_turn(message)
        return {"ok": True}

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        exchange.record_audit(payload)
        return {"ok": True}

    @mcp.tool
    def receive_control(message: dict) -> dict:
        exchange.record_control(message)
        return {"ok": True}
