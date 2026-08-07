"""FastMCP server (PRD_2 §2.1, §3; extended PRD_6 §3): this peer's inbound
half. Exposes tools the Cop's client calls. `ping` is Stage 2's stand-in for
the real `receive_turn` tool (still arriving in a later stage); `submit_audit`
(Stage 6) is real -- it cross-verifies the *caller's* revealed log against
their own earlier commits, never a peer self-verifying its own history
(PRD_6 §2.3: the audit's entire value comes from the other side checking).
"""

import socket
import time

from fastmcp import FastMCP

from thief_peer.domain.crypto import audit_records
from thief_peer.exceptions import TransportError


def _ensure_port_free(host: str, port: int) -> None:
    """Fail fast (PRD_2 §3 Startup row) instead of letting FastMCP's own
    bind error surface as a bare, unhandled socket exception."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise TransportError(
            f"Port {port} on {host} is already in use — cannot start "
            f"the Thief MCP server there."
        ) from exc
    finally:
        probe.close()


def _ping_handler(payload: dict) -> dict:
    """Plain, directly-testable logic behind the `ping` tool (PRD_2 §2.2:
    validate before trusting, even for this minimal echo)."""
    if not isinstance(payload, dict):
        raise TypeError(f"ping payload must be a dict, got {type(payload).__name__}")
    return {"pong": True, "received": payload}


def _submit_audit_handler(payload: dict) -> dict:
    """Cross-verification only (PRD_6 §2.3): we are the *receiver* here,
    re-verifying the caller's own revealed log against the commits they
    already sent during play -- never a peer self-verifying its own
    history, which would be logically vacuous for a genuine cheater."""
    if not isinstance(payload, dict) or "records" not in payload:
        raise TypeError("submit_audit payload must be a dict with a 'records' list")
    return audit_records(payload["records"])


def build_server(port: int, host: str = "0.0.0.0") -> FastMCP:
    _ensure_port_free(host, port)

    mcp = FastMCP(name="thief-peer")

    @mcp.tool
    def ping(payload: dict) -> dict:
        return _ping_handler(payload)

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        return _submit_audit_handler(payload)

    return mcp


def wait_until_ready(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> None:
    """Block until a server started on `port` (e.g. in another thread) is
    accepting connections, or raise `TransportError` after `timeout`
    seconds — used by callers that must not call the server before it has
    finished starting up (smoke tests, integration tests)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if probe.connect_ex((host, port)) == 0:
                return
        finally:
            probe.close()
        time.sleep(0.05)
    raise TransportError(f"Server on {host}:{port} never became ready within {timeout}s")
