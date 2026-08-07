"""Stage 2 integration test (PRD_2 §5): a real FastMCP server, started in
its own thread, and a real McpTransport client talking to it over an actual
localhost socket — no mocking. This is what "no central server, two peers
exchange a raw JSON message over localhost" (TODO.md Stage 2 milestone)
actually looks like end to end.
"""

import socket
import threading

import pytest

from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import build_server, wait_until_ready


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_server():
    port = _free_port()
    app = build_server(port)
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


def test_client_pings_real_server_and_gets_echo(running_server):
    transport = McpTransport(f"http://127.0.0.1:{running_server}/mcp")
    result = transport.call("ping", {"payload": {"hello": "world"}})
    assert result == {"pong": True, "received": {"hello": "world"}}
