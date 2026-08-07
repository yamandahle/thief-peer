"""infra/mcp_client.py unit tests. McpTransport is exercised against an
unreachable URL here (no real server needed) to prove it raises our own
TransportError instead of leaking a bare connection exception (PRD_2 §3,
McpTransport.call row). The real round trip against a live server is
covered by the Stage-2 integration test."""

import pytest

from thief_peer.exceptions import TransportError
from thief_peer.infra.mcp_client import McpTransport


def test_init_stores_url_without_connecting(unused_tcp_port):
    # No server is running on this port — construction must not raise.
    transport = McpTransport(f"http://127.0.0.1:{unused_tcp_port}/mcp")
    assert transport.opponent_url == f"http://127.0.0.1:{unused_tcp_port}/mcp"


def test_call_against_unreachable_url_raises_transport_error(unused_tcp_port):
    transport = McpTransport(f"http://127.0.0.1:{unused_tcp_port}/mcp")
    with pytest.raises(TransportError):
        transport.call("ping", {"hello": "world"})


@pytest.fixture
def unused_tcp_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]
