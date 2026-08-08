"""FastMCP server (PRD_2 §2.1, §3; extended PRD_6 §3, PRD_8 §3): this peer's
inbound half. Exposes tools the Cop's client calls. `ping` is Stage 2's
diagnostic echo; `submit_audit` (Stage 6) cross-verifies the *caller's*
revealed log against their own earlier commits, never a peer self-verifying
its own history (PRD_6 §2.3). `negotiate`/`receive_control`/`commit_move`/
`reveal_move` (Stage 8) are the real live-match tools -- each is a one-line
delegation to `context.handle_*`, keeping this file pure routing; the
context (normally `PeerRuntime` itself) owns all the actual state/logic.
`get_revealed_records` (post-Stage-8 fix) is the other half of a genuinely
*mutual* audit (rules 19/36): `submit_audit` lets the opponent audit us;
this lets us actively pull the opponent's own revealed log to audit them,
rather than only ever submitting ourselves and passively hoping they
reciprocate.
"""

import socket
import threading
import time

from fastmcp import FastMCP

from thief_peer.domain.crypto import audit_records
from thief_peer.exceptions import TransportError
from thief_peer.infra.null_peer_context import NullPeerContext

__all__ = [
    "NullPeerContext",
    "build_server",
    "run_server_in_background",
    "wait_until_ready",
]


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


def build_server(port: int, context, host: str = "0.0.0.0") -> FastMCP:
    _ensure_port_free(host, port)

    mcp = FastMCP(name="thief-peer")

    @mcp.tool
    def ping(payload: dict) -> dict:
        return _ping_handler(payload)

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        return _submit_audit_handler(payload)

    @mcp.tool
    def negotiate(terms: dict, nonce: str, commit: str) -> dict:
        # peer/handshake.py's run_handshake (reused unmodified) sends these
        # three fields as loose top-level arguments, not wrapped in a
        # `payload` key -- matches its existing, already-tested call shape.
        return context.handle_negotiate({"terms": terms, "nonce": nonce, "commit": commit})

    @mcp.tool
    def receive_control(type: str, record: dict) -> dict:
        # parameter named `type` to match run_handshake's own dict key exactly
        return context.handle_receive_control({"type": type, "record": record})

    @mcp.tool
    def commit_move(payload: dict) -> dict:
        return context.handle_commit_move(payload)

    @mcp.tool
    def reveal_move(payload: dict) -> dict:
        return context.handle_reveal_move(payload)

    @mcp.tool
    def get_revealed_records(payload: dict) -> dict:
        return context.handle_get_revealed_records(payload)

    return mcp


def run_server_in_background(app: FastMCP, port: int) -> threading.Thread:
    """Starts `app` on a daemon thread and blocks until it's accepting
    connections -- the exact thread-plus-`wait_until_ready` pattern already
    duplicated across every Stage 2-7 integration test fixture, now shared
    for `peer/runtime.py`'s production use (PRD_8 §3)."""
    thread = threading.Thread(
        target=app.run,
        kwargs={
            "transport": "http",
            "host": "0.0.0.0",
            "port": port,
            "show_banner": False,
            "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    wait_until_ready(port)
    return thread


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
