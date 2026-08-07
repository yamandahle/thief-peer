"""infra/mcp_client.py unit tests. McpTransport is exercised against an
unreachable URL (no real server needed) and against monkeypatched
`_call_async` stubs to control retry/backoff/deadline timing precisely and
fast, without depending on real socket-refusal latency (PRD_5 §3, §5). The
real round trip against a live server is covered by the Stage-2/3/4
integration tests."""

import asyncio

import pytest

from thief_peer.exceptions import DeadlineExceededError, TransportError
from thief_peer.infra.mcp_client import McpTransport

# Small, fast values for every test -- config-driven per-instance, never a
# hardcoded module constant (PRD_5 §5's "no hardcoded timeout values" bar).
# _FAST_DEADLINE is deliberately generous (not "fast"): a real fastmcp
# Client's own internal connection retries against a truly unreachable
# address take a few seconds per attempt on their own, before our retry
# loop even gets a chance to run again -- too small a deadline here would
# make every attempt look like a timeout instead of a connection failure.
_FAST_BACKOFF = 0.01
_FAST_RETRIES = 3
_FAST_DEADLINE = 15.0


def test_init_stores_url_without_connecting(unused_tcp_port):
    # No server is running on this port — construction must not raise.
    transport = McpTransport(f"http://127.0.0.1:{unused_tcp_port}/mcp")
    assert transport.opponent_url == f"http://127.0.0.1:{unused_tcp_port}/mcp"


def test_call_against_unreachable_url_raises_transport_error(unused_tcp_port):
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=_FAST_BACKOFF,
        max_retries=_FAST_RETRIES,
        response_timeout_sec=_FAST_DEADLINE,
    )
    with pytest.raises(TransportError):
        transport.call("ping", {"hello": "world"})


def test_call_retries_exactly_max_retries_and_names_url_and_attempts(unused_tcp_port):
    url = f"http://127.0.0.1:{unused_tcp_port}/mcp"
    transport = McpTransport(
        url, retry_backoff_sec=_FAST_BACKOFF, max_retries=_FAST_RETRIES, response_timeout_sec=_FAST_DEADLINE
    )
    calls = []

    async def _always_fails(tool_name, payload):
        calls.append(1)
        raise ConnectionError("refused")

    transport._call_async = _always_fails

    with pytest.raises(TransportError) as exc_info:
        transport.call("ping", {"hello": "world"})

    assert len(calls) == _FAST_RETRIES
    assert url in str(exc_info.value)
    assert str(_FAST_RETRIES) in str(exc_info.value)


def test_call_succeeds_after_a_transient_failure_within_retry_budget(unused_tcp_port):
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=_FAST_BACKOFF,
        max_retries=_FAST_RETRIES,
        response_timeout_sec=_FAST_DEADLINE,
    )
    calls = []

    async def _fails_once_then_succeeds(tool_name, payload):
        calls.append(1)
        if len(calls) < 2:
            raise ConnectionError("refused")
        return {"ok": True}

    transport._call_async = _fails_once_then_succeeds

    result = transport.call("ping", {"hello": "world"})

    assert result == {"ok": True}
    assert len(calls) == 2


def test_call_uses_linear_backoff_between_attempts(monkeypatch, unused_tcp_port):
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=1.0,
        max_retries=3,
        response_timeout_sec=_FAST_DEADLINE,
    )

    async def _always_fails(tool_name, payload):
        raise ConnectionError("refused")

    transport._call_async = _always_fails

    sleeps = []
    monkeypatch.setattr("thief_peer.infra.mcp_client.time.sleep", lambda s: sleeps.append(s))

    with pytest.raises(TransportError):
        transport.call("ping", {})

    # linear: backoff * attempt_number, for the 2 gaps between 3 attempts
    assert sleeps == [1.0, 2.0]


def test_call_raises_deadline_exceeded_when_it_hangs_past_the_timeout(unused_tcp_port):
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=_FAST_BACKOFF,
        max_retries=_FAST_RETRIES,
        response_timeout_sec=0.2,
    )

    async def _hangs_forever(tool_name, payload):
        await asyncio.sleep(10)
        return {"unreachable": True}

    transport._call_async = _hangs_forever

    with pytest.raises(DeadlineExceededError):
        transport.call("ping", {})


@pytest.fixture
def unused_tcp_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]
