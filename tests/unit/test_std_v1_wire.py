"""interop/std_v1/wire.py tests -- confirms every call wraps this side's
dict inside the exact named argument the spec's own tool signatures
expect (Section 7), not passed as bare kwargs."""

from thief_peer.interop.std_v1.wire import send_audit, send_control, send_negotiate, send_turn


class _SpyTransport:
    def __init__(self):
        self.calls = []

    def call(self, tool_name, payload, retryable=True):
        self.calls.append((tool_name, payload, retryable))
        return {"ok": True}


def test_send_negotiate_wraps_the_offer_as_message():
    transport = _SpyTransport()
    send_negotiate(transport, {"group_id": "g"})
    assert transport.calls == [("negotiate", {"message": {"group_id": "g"}}, True)]


def test_send_turn_wraps_as_message():
    transport = _SpyTransport()
    send_turn(transport, {"step": 1})
    assert transport.calls == [("receive_turn", {"message": {"step": 1}}, True)]


def test_send_audit_wraps_as_payload_not_message():
    transport = _SpyTransport()
    send_audit(transport, {"sender": "thief"})
    assert transport.calls == [("submit_audit", {"payload": {"sender": "thief"}}, True)]


def test_send_control_wraps_as_message():
    transport = _SpyTransport()
    send_control(transport, {"type": "ping"})
    assert transport.calls == [("receive_control", {"message": {"type": "ping"}}, True)]


def test_every_call_is_retryable():
    transport = _SpyTransport()
    send_negotiate(transport, {})
    send_turn(transport, {})
    send_audit(transport, {})
    send_control(transport, {})
    assert all(retryable is True for _name, _payload, retryable in transport.calls)
