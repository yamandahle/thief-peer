"""infra/mcp_client.py unit tests. McpTransport is exercised against an
unreachable URL (no real server needed) and against monkeypatched
`_call_async` stubs to control retry/backoff/deadline timing precisely and
fast, without depending on real socket-refusal latency (PRD_5 §3, §5). The
real round trip against a live server is covered by the Stage-2/3/4
integration tests."""

import asyncio
import threading

import httpx
import pytest

from thief_peer.exceptions import DeadlineExceededError, TransportError
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import NullPeerContext, build_server, wait_until_ready

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
        raise httpx.ConnectError("refused")

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
            raise httpx.ConnectError("refused")
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
        raise httpx.ConnectError("refused")

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


def test_call_reuses_one_client_across_many_calls_not_one_per_call(monkeypatch, unused_tcp_port):
    # The actual bug this closes: the old design opened a fresh
    # fastmcp.Client (and a fresh asyncio event loop) on every single
    # call -- found live via a real cross-machine match where connection
    # churn over a real ngrok tunnel (never reproduced on localhost, where
    # a fresh connection is near-instant) failed mid-match with "Client
    # failed to connect", inside receive_capture_claim's own synchronous
    # reply.
    import thief_peer.infra.mcp_client as mcp_client_module

    construct_count = {"n": 0}
    original_init = mcp_client_module.Client.__init__

    def _counting_init(self, *args, **kwargs):
        construct_count["n"] += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(mcp_client_module.Client, "__init__", _counting_init)

    context = NullPeerContext()
    app = build_server(unused_tcp_port, context)
    threading.Thread(
        target=app.run,
        kwargs={
            "transport": "http", "host": "127.0.0.1", "port": unused_tcp_port,
            "show_banner": False, "log_level": "warning",
        },
        daemon=True,
    ).start()
    wait_until_ready(unused_tcp_port)

    transport = McpTransport(f"http://127.0.0.1:{unused_tcp_port}/mcp")
    try:
        for _ in range(5):
            result = transport.call("ping", {"payload": {"hello": "world"}})
            assert result == {"pong": True, "received": {"hello": "world"}}
    finally:
        transport.close()

    assert construct_count["n"] == 1, (
        f"expected exactly one fastmcp.Client construction across 5 calls, got {construct_count['n']}"
    )


def test_call_retries_on_connect_timeout_too(unused_tcp_port):
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=_FAST_BACKOFF,
        max_retries=_FAST_RETRIES,
        response_timeout_sec=_FAST_DEADLINE,
    )
    calls = []

    async def _always_times_out(tool_name, payload):
        calls.append(1)
        raise httpx.ConnectTimeout("timed out connecting")

    transport._call_async = _always_times_out

    with pytest.raises(TransportError):
        transport.call("ping", {})

    assert len(calls) == _FAST_RETRIES


@pytest.mark.parametrize(
    "message",
    ["Client failed to connect: refused", "Client is not connected. Use 'async with client:'"],
)
def test_call_retries_on_fastmcps_own_pre_transmission_runtime_errors(unused_tcp_port, message):
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=_FAST_BACKOFF,
        max_retries=_FAST_RETRIES,
        response_timeout_sec=_FAST_DEADLINE,
    )
    calls = []

    async def _always_fails(tool_name, payload):
        calls.append(1)
        raise RuntimeError(message)

    transport._call_async = _always_fails

    with pytest.raises(TransportError):
        transport.call("ping", {})

    assert len(calls) == _FAST_RETRIES


def test_call_does_not_retry_a_failure_that_might_mean_the_request_was_sent(unused_tcp_port):
    # receive_commit/receive_reveal on the far side aren't idempotent -- a
    # failure that isn't provably pre-transmission (e.g. the connection
    # drops while awaiting the response) must not be silently resent, or
    # the peer's step counter could double-advance. docs/todoFIXMCP.md #1.
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=_FAST_BACKOFF,
        max_retries=_FAST_RETRIES,
        response_timeout_sec=_FAST_DEADLINE,
    )
    calls = []

    async def _fails_ambiguously(tool_name, payload):
        calls.append(1)
        raise RuntimeError("connection reset while awaiting response")

    transport._call_async = _fails_ambiguously

    with pytest.raises(TransportError):
        transport.call("receive_commit", {"h_commit": "abc"})

    assert len(calls) == 1  # no retry -- first attempt's failure was final


def test_call_does_not_sleep_for_backoff_on_an_unsafe_failure(monkeypatch, unused_tcp_port):
    transport = McpTransport(
        f"http://127.0.0.1:{unused_tcp_port}/mcp",
        retry_backoff_sec=1.0,
        max_retries=3,
        response_timeout_sec=_FAST_DEADLINE,
    )

    async def _fails_ambiguously(tool_name, payload):
        raise ValueError("some unrelated bug, not a connection failure")

    transport._call_async = _fails_ambiguously

    sleeps = []
    monkeypatch.setattr("thief_peer.infra.mcp_client.time.sleep", lambda s: sleeps.append(s))

    with pytest.raises(TransportError):
        transport.call("ping", {})

    assert sleeps == []


def test_concurrent_calls_open_the_session_exactly_once(unused_tcp_port):
    # Real bug found live (yanell11 match): two calls submitted close
    # together both saw `not self._connected` before either finished
    # `__aenter__()`, so both opened a session -- the peer's MCP server
    # correctly rejected the second SSE stream with 409, since the
    # Streamable HTTP transport allows exactly one per session.
    transport = McpTransport(f"http://127.0.0.1:{unused_tcp_port}/mcp")

    aenter_calls = []

    class _FakeClient:
        async def __aenter__(self):
            aenter_calls.append(1)
            # Widen the race window: without the lock, a second coroutine
            # scheduled on the same loop gets a chance to run its own
            # `not self._connected` check right here, before this one sets
            # `self._connected = True`.
            await asyncio.sleep(0.05)

        async def call_tool(self, tool_name, payload):
            class _Result:
                data = {"ok": True, "tool": tool_name}

            return _Result()

        async def close(self):
            pass

    transport._client = _FakeClient()

    async def _fire_two_concurrent_calls():
        await asyncio.gather(
            transport._call_async("negotiate", {"n": 1}),
            transport._call_async("negotiate", {"n": 2}),
        )

    future = asyncio.run_coroutine_threadsafe(_fire_two_concurrent_calls(), transport._loop)
    future.result(timeout=5)

    assert aenter_calls == [1], f"expected exactly one __aenter__ call, got {len(aenter_calls)}"


def test_close_is_idempotent_and_safe_with_no_prior_connection(unused_tcp_port):
    transport = McpTransport(f"http://127.0.0.1:{unused_tcp_port}/mcp")  # never called
    transport.close()
    transport.close()  # second call must not raise


@pytest.fixture
def unused_tcp_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]
