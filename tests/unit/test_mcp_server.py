"""infra/mcp_server.py unit tests. The ping tool's logic is factored into
a plain, directly-testable function (`_ping_handler`) so we don't need a
running server just to test the echo behavior — the real round-trip over
the wire is covered separately by the Stage-2 integration test."""

import socket

import pytest

from thief_peer.exceptions import TransportError
from thief_peer.infra.mcp_server import _ping_handler, build_server, wait_until_ready


def test_ping_handler_echoes_payload_with_pong_true():
    result = _ping_handler({"hello": "world"})
    assert result == {"pong": True, "received": {"hello": "world"}}


def test_ping_handler_rejects_non_dict_payload():
    with pytest.raises(TypeError):
        _ping_handler("not a dict")  # type: ignore[arg-type]


def test_build_server_returns_an_app_bound_to_the_requested_port(unused_tcp_port):
    app = build_server(unused_tcp_port)
    assert app is not None


def test_build_server_fails_fast_if_port_already_in_use(unused_tcp_port):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("0.0.0.0", unused_tcp_port))
    try:
        with pytest.raises(TransportError, match=str(unused_tcp_port)):
            build_server(unused_tcp_port)
    finally:
        blocker.close()


def test_wait_until_ready_returns_once_something_listens(unused_tcp_port):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", unused_tcp_port))
    listener.listen(1)
    try:
        wait_until_ready(unused_tcp_port, timeout=2.0)
    finally:
        listener.close()


def test_wait_until_ready_raises_transport_error_on_timeout(unused_tcp_port):
    with pytest.raises(TransportError):
        wait_until_ready(unused_tcp_port, timeout=0.2)


@pytest.fixture
def unused_tcp_port() -> int:
    """A free localhost port, picked by the OS, released before use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]
