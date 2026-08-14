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
        self.retryable_flags = []
        self._response = response if response is not None else {"acknowledged": True}

    def call(self, tool_name, payload, retryable=True):
        self.calls.append((tool_name, payload))
        self.retryable_flags.append(retryable)
        return self._response


def test_cop_send_commit_calls_receive_commit_with_flat_kwarg(monkeypatch):
    monkeypatch.setattr("thief_peer.interop.cop_turn_sender.time.time", lambda: 1000.0)
    transport = _SpyTransport()
    cop_send_commit(transport, "abc123", deadline_sec=30.0)
    assert transport.calls == [
        ("receive_commit", {"h_commit": "abc123", "sent_at": 1000.0, "deadline_at": 1030.0})
    ]


def test_cop_send_reveal_wraps_the_move_as_her_typed_dict(monkeypatch):
    monkeypatch.setattr("thief_peer.interop.cop_turn_sender.time.time", lambda: 1000.0)
    transport = _SpyTransport()
    cop_send_reveal(transport, "N", "cold, near the wall", deadline_sec=30.0)
    assert transport.calls == [
        (
            "receive_reveal",
            {
                "move": {"type": "move", "direction": "N"},
                "hint_text": "cold, near the wall",
                "sent_at": 1000.0,
                "deadline_at": 1030.0,
            },
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


def test_every_per_round_state_mutating_call_opts_out_of_retry():
    # infra/mcp_client.py's own docstring: retrying a per-round state-
    # mutating call could land on her server twice and fold the same
    # evidence into her belief map twice.
    transport = _SpyTransport()

    cop_send_commit(transport, "abc123", deadline_sec=30.0)
    cop_send_reveal(transport, "N", "cold", deadline_sec=30.0)
    cop_send_barrier_declaration(transport, row=1, col=1)
    cop_send_capture_claim(transport, thief_row=1, thief_col=1, cop_row=1, cop_col=1, claimed_at_step=1)
    cop_send_capture_response(transport, confirmed=True, true_thief_row=1, true_thief_col=1)

    assert transport.retryable_flags == [False] * 5


def test_cop_send_final_reveal_and_the_scent_pull_stay_retryable():
    # Unlike the per-round calls above, receive_final_reveal just records
    # nonces/intents and reruns the audit against the same trace log
    # either way -- retrying it is provably harmless, and was found
    # necessary by a real batch of automated local matches hitting a
    # transient connection failure right at this exact call.
    transport = _SpyTransport()
    cop_send_final_reveal(transport, {}, {})
    assert transport.retryable_flags == [True]

    transport = _SpyTransport(response={"cells": []})
    cop_request_scent_map(transport)
    assert transport.retryable_flags == [True]
