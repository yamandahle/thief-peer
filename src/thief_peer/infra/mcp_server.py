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
reciprocate. `receive_barrier_declaration`/`receive_capture_claim`
(also post-Stage-8) close rules 21/22/46's gap -- `domain/rules.py`'s
`is_captured_by_barrier` existed but had no wire channel to ever learn a
barrier was placed at all.
"""

import socket

from fastmcp import FastMCP

from thief_peer.domain.crypto import audit_records
from thief_peer.exceptions import TransportError
from thief_peer.infra.null_peer_context import NullPeerContext
from thief_peer.infra.server_lifecycle import run_server_in_background, wait_until_ready

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
    def negotiate(terms: dict, nonce: str, commit: str, scent_lock_hash: str) -> dict:
        # peer/handshake.py's run_handshake (reused unmodified) sends these
        # fields as loose top-level arguments, not wrapped in a `payload`
        # key -- matches its existing, already-tested call shape.
        # scent_lock_hash (ch.4.5) rides alongside terms/nonce/commit --
        # verification happens client-side in handshake.py, the server just
        # needs to accept the field so the caller's call shape is legal.
        return context.handle_negotiate(
            {"terms": terms, "nonce": nonce, "commit": commit, "scent_lock_hash": scent_lock_hash}
        )

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

    @mcp.tool
    def receive_barrier_declaration(payload: dict) -> dict:
        return context.handle_receive_barrier_declaration(payload)

    @mcp.tool
    def receive_capture_claim(payload: dict) -> dict:
        return context.handle_receive_capture_claim(payload)

    return mcp
