"""interop/cop_turn_sender.py tests: each function must call the exact
tool name/payload shape her real MCP server exposes (verified against her
cloned `tools/mcp_server*.py` signatures), not our own native vocabulary."""

from thief_peer.interop.cop_turn_sender import (
    cop_request_scent_map,
    cop_send_barrier_declaration,
    cop_send_capture_claim,
    cop_send_capture_response,
    cop_send_commit,
    cop_send_final_reveal,
    cop_send_reveal,
)


class _SpyTransport:
    def __init__(self, response=None):
        self.calls = []
        self._response = response if response is not None else {"acknowledged": True}

    def call(self, tool_name, payload):
        self.calls.append((tool_name, payload))
        return self._response


def test_cop_send_commit_calls_receive_commit_with_flat_kwarg():
    transport = _SpyTransport()
    cop_send_commit(transport, "abc123")
    assert transport.calls == [("receive_commit", {"h_commit": "abc123"})]


def test_cop_send_reveal_wraps_the_move_as_her_typed_dict():
    transport = _SpyTransport()
    cop_send_reveal(transport, "N", "cold, near the wall")
    assert transport.calls == [
        (
            "receive_reveal",
            {"move": {"type": "move", "direction": "N"}, "hint_text": "cold, near the wall"},
        )
    ]


def test_cop_request_scent_map_calls_with_empty_payload_and_deserializes():
    transport = _SpyTransport(response={"cells": [[3, 4, 0.62]]})
    result = cop_request_scent_map(transport)

    assert transport.calls == [("share_scent_map", {})]
    assert result == {"4,3": 0.62}


def test_cop_send_final_reveal_sends_nonces_and_intents():
    transport = _SpyTransport()
    cop_send_final_reveal(transport, {"0": "nonce0"}, {"0": True})
    assert transport.calls == [
        ("receive_final_reveal", {"nonces": {"0": "nonce0"}, "intents": {"0": True}})
    ]


def test_cop_send_barrier_declaration_sends_col_then_row_named_kwargs():
    transport = _SpyTransport()
    cop_send_barrier_declaration(transport, row=2, col=5)
    assert transport.calls == [("receive_barrier_declaration", {"col": 5, "row": 2})]


def test_cop_send_capture_claim_sends_all_five_flat_fields():
    transport = _SpyTransport()
    cop_send_capture_claim(transport, thief_row=1, thief_col=2, cop_row=3, cop_col=4, claimed_at_step=9)
    assert transport.calls == [
        (
            "receive_capture_claim",
            {"thief_col": 2, "thief_row": 1, "cop_col": 4, "cop_row": 3, "claimed_at_step": 9},
        )
    ]


def test_cop_send_capture_response_sends_confirmed_and_true_position():
    transport = _SpyTransport()
    cop_send_capture_response(transport, confirmed=True, true_thief_row=1, true_thief_col=2)
    assert transport.calls == [
        (
            "receive_capture_response",
            {"confirmed": True, "true_thief_col": 2, "true_thief_row": 1},
        )
    ]
