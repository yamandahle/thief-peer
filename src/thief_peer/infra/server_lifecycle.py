"""Server startup/readiness helpers -- split out of `infra/mcp_server.py`
(which owns tool routing, a separate concern) to stay under this codebase's
file-length convention.
"""

import socket
import threading
import time

from fastmcp import FastMCP

from thief_peer.exceptions import TransportError


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
