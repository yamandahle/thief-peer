"""infra/mcp_server.py unit tests. The ping tool's logic is factored into
a plain, directly-testable function (`_ping_handler`) so we don't need a
running server just to test the echo behavior — the real round-trip over
the wire is covered separately by the Stage-2 integration test. The Stage-8
tools (negotiate/receive_control/commit_move/reveal_move) delegate straight
to a `context` object (PRD_8 §3), so they're exercised over a real live
round trip against a spy context here -- that delegation IS the tool's only
logic, so a real routing test is what actually proves it's wired."""

import socket
import threading

import pytest

from thief_peer.domain.crypto import CommitReveal
from thief_peer.exceptions import TransportError
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import (
    NullPeerContext,
    _ping_handler,
    _submit_audit_handler,
    build_server,
    run_server_in_background,
    wait_until_ready,
)


def test_ping_handler_echoes_payload_with_pong_true():
    result = _ping_handler({"hello": "world"})
    assert result == {"pong": True, "received": {"hello": "world"}}


def test_ping_handler_rejects_non_dict_payload():
    with pytest.raises(TypeError):
        _ping_handler("not a dict")  # type: ignore[arg-type]


def _sealed_record(state="s", move="N", intent="truth"):
    payload = {"state": state, "move": move, "intent": intent}
    sealed = CommitReveal.seal(payload)
    return {"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]}


def test_submit_audit_handler_passes_a_clean_log():
    records = [_sealed_record(state=f"s{i}") for i in range(3)]
    result = _submit_audit_handler({"sender": "thief", "records": records})

    assert result == {"passed": True, "verified_steps": 3, "failed_steps": []}


def test_submit_audit_handler_catches_a_tampered_record():
    records = [_sealed_record(state=f"s{i}") for i in range(3)]
    records[1]["payload"]["move"] = "S"  # tampered after sealing

    result = _submit_audit_handler({"sender": "thief", "records": records})

    assert result["passed"] is False
    assert result["failed_steps"] == [1]


def test_submit_audit_handler_rejects_a_payload_without_records():
    with pytest.raises(TypeError):
        _submit_audit_handler({"sender": "thief"})


def test_submit_audit_handler_rejects_non_dict_payload():
    with pytest.raises(TypeError):
        _submit_audit_handler("not a dict")  # type: ignore[arg-type]


def test_build_server_returns_an_app_bound_to_the_requested_port(unused_tcp_port):
    app = build_server(unused_tcp_port, NullPeerContext())
    assert app is not None


def test_build_server_fails_fast_if_port_already_in_use(unused_tcp_port):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("0.0.0.0", unused_tcp_port))
    try:
        with pytest.raises(TransportError, match=str(unused_tcp_port)):
            build_server(unused_tcp_port, NullPeerContext())
    finally:
        blocker.close()


class _SpyContext:
    def __init__(self):
        self.calls = []

    def handle_negotiate(self, payload):
        self.calls.append(("negotiate", payload))
        return {"terms": {"grid_size": 7}, "nonce": "n", "commit": "c"}

    def handle_receive_control(self, payload):
        self.calls.append(("receive_control", payload))
        return {"record": {"group_name": "Cop-Team"}}

    def handle_commit_move(self, payload):
        self.calls.append(("commit_move", payload))
        return {"ok": True}

    def handle_reveal_move(self, payload):
        self.calls.append(("reveal_move", payload))
        return {"ok": True}

    def handle_get_revealed_records(self, payload):
        self.calls.append(("get_revealed_records", payload))
        return {"records": [{"payload": {"state": "s"}, "commit": "c"}]}

    def handle_receive_barrier_declaration(self, payload):
        self.calls.append(("receive_barrier_declaration", payload))
        return {"ok": True}

    def handle_receive_capture_claim(self, payload):
        self.calls.append(("receive_capture_claim", payload))
        return {"confirmed": True}


@pytest.fixture
def live_server_with_spy_context(unused_tcp_port):
    context = _SpyContext()
    app = build_server(unused_tcp_port, context)
    thread = threading.Thread(
        target=app.run,
        kwargs={
            "transport": "http",
            "host": "127.0.0.1",
            "port": unused_tcp_port,
            "show_banner": False,
            "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    wait_until_ready(unused_tcp_port)
    yield unused_tcp_port, context


def test_negotiate_tool_delegates_to_context_and_returns_its_result(live_server_with_spy_context):
    # peer/handshake.py's run_handshake sends these as loose top-level
    # arguments (Negotiation.signed()'s own shape), not wrapped in `payload`.
    port, context = live_server_with_spy_context
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = transport.call("negotiate", {"terms": {"grid_size": 7}, "nonce": "x", "commit": "y"})

    assert result == {"terms": {"grid_size": 7}, "nonce": "n", "commit": "c"}
    assert context.calls == [("negotiate", {"terms": {"grid_size": 7}, "nonce": "x", "commit": "y"})]


def test_receive_control_tool_delegates_to_context_and_returns_its_result(live_server_with_spy_context):
    # peer/handshake.py sends {"type": ..., "record": ...} as loose
    # top-level arguments, matching this tool's own parameter names.
    port, context = live_server_with_spy_context
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = transport.call("receive_control", {"type": "step0", "record": {"a": 1}})

    assert result == {"record": {"group_name": "Cop-Team"}}
    assert context.calls == [("receive_control", {"type": "step0", "record": {"a": 1}})]


def test_commit_move_tool_delegates_to_context_and_returns_its_result(live_server_with_spy_context):
    port, context = live_server_with_spy_context
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")
    sent = {"step": 1, "sender": "cop", "h_commit": "abc"}

    result = transport.call("commit_move", {"payload": sent})

    assert result == {"ok": True}
    assert context.calls == [("commit_move", sent)]


def test_reveal_move_tool_delegates_to_context_and_returns_its_result(live_server_with_spy_context):
    port, context = live_server_with_spy_context
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")
    sent = {"step": 1, "sender": "cop", "hint": "h", "scent_grid": {}, "move": "N", "intent": "truth"}

    result = transport.call("reveal_move", {"payload": sent})

    assert result == {"ok": True}
    assert context.calls == [("reveal_move", sent)]


def test_get_revealed_records_tool_delegates_to_context_and_returns_its_result(
    live_server_with_spy_context,
):
    port, context = live_server_with_spy_context
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = transport.call("get_revealed_records", {"payload": {}})

    assert result == {"records": [{"payload": {"state": "s"}, "commit": "c"}]}
    assert context.calls == [("get_revealed_records", {})]


def test_receive_barrier_declaration_tool_delegates_to_context_and_returns_its_result(
    live_server_with_spy_context,
):
    port, context = live_server_with_spy_context
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")
    sent = {"row": 3, "col": 4}

    result = transport.call("receive_barrier_declaration", {"payload": sent})

    assert result == {"ok": True}
    assert context.calls == [("receive_barrier_declaration", sent)]


def test_receive_capture_claim_tool_delegates_to_context_and_returns_its_result(
    live_server_with_spy_context,
):
    port, context = live_server_with_spy_context
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")
    sent = {"reason": "barrier"}

    result = transport.call("receive_capture_claim", {"payload": sent})

    assert result == {"confirmed": True}
    assert context.calls == [("receive_capture_claim", sent)]


def test_null_peer_context_raises_not_implemented_for_every_handler():
    context = NullPeerContext()
    for method_name in (
        "handle_negotiate",
        "handle_receive_control",
        "handle_commit_move",
        "handle_reveal_move",
        "handle_get_revealed_records",
        "handle_receive_barrier_declaration",
        "handle_receive_capture_claim",
    ):
        with pytest.raises(NotImplementedError):
            getattr(context, method_name)({})


def test_run_server_in_background_starts_a_reachable_server(unused_tcp_port):
    app = build_server(unused_tcp_port, NullPeerContext())

    run_server_in_background(app, unused_tcp_port)

    transport = McpTransport(f"http://127.0.0.1:{unused_tcp_port}/mcp")
    assert transport.call("ping", {"payload": {"hi": "there"}}) == {"pong": True, "received": {"hi": "there"}}


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
