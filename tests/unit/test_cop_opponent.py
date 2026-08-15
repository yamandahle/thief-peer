"""interop/cop_opponent.py tests: cop_shutdown_grace, found necessary by an
actual live run against the Cop repo's real process -- her own
report_game() always calls this side's receive_final_reveal, even though
this side's own finalize_match skips the audit exchange and returns
immediately in cop_v1 mode. Without waiting for it, this process exits
(tearing down its server) before her call has anywhere to land -- proven
by a real run where even a blind 5s sleep wasn't long enough, hence the
event-driven wait rather than a guessed fixed duration. The post-event
flush sleep (RESPONSE_FLUSH_SECONDS) was also found necessary by a live
run: the event fires before FastMCP has flushed her HTTP response, so
exiting the instant it fires still cut her connection mid-response."""

import threading

from thief_peer.interop.cop_opponent import (
    cop_shutdown_grace,
    play_opponent_round,
    send_opponent_final_reveal,
)


class _FakeAdapter:
    def __init__(self):
        self.final_reveal_received = threading.Event()


class _FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, name, payload):
        self.calls.append((name, payload))
        return {"acknowledged": True}


class _FakeRuntime:
    def __init__(self, opponent_protocol):
        self.opponent_protocol = opponent_protocol
        self._cop_adapter = _FakeAdapter()
        self.transport = _FakeTransport()


def test_cop_shutdown_grace_returns_once_the_event_fires_plus_the_flush_buffer(monkeypatch):
    monkeypatch.setattr("thief_peer.interop.cop_opponent.RESPONSE_FLUSH_SECONDS", 0.01)
    runtime = _FakeRuntime("cop_v1")
    runtime._cop_adapter.final_reveal_received.set()  # her call already landed

    cop_shutdown_grace(runtime)  # must not block on the ceiling


def test_cop_shutdown_grace_respects_the_ceiling_if_the_event_never_fires(monkeypatch):
    monkeypatch.setattr("thief_peer.interop.cop_opponent.SHUTDOWN_GRACE_CEILING_SECONDS", 0.05)
    monkeypatch.setattr("thief_peer.interop.cop_opponent.RESPONSE_FLUSH_SECONDS", 0.01)
    runtime = _FakeRuntime("cop_v1")

    cop_shutdown_grace(runtime)  # returns after the (shortened) ceiling, not forever


def test_cop_shutdown_grace_does_nothing_in_native_mode():
    runtime = _FakeRuntime("native")

    cop_shutdown_grace(runtime)  # must not touch _cop_adapter at all (it's unset for native)


def test_send_opponent_final_reveal_sends_nonces_and_intents_in_cop_v1_mode():
    runtime = _FakeRuntime("cop_v1")
    records = [
        {"payload": {"step": 1, "nonce": "n1", "intent": True}},
        {"payload": {"step": 2, "nonce": "n2", "intent": False}},
    ]

    result = send_opponent_final_reveal(runtime, records)

    assert runtime.transport.calls == [
        (
            "receive_final_reveal",
            {"nonces": {"1": "n1", "2": "n2"}, "intents": {"1": True, "2": False}},
        )
    ]
    assert result["passed"] is False  # stub transport returns ack-only
    assert result["verified_steps"] == 0


def test_send_opponent_final_reveal_does_nothing_in_native_mode():
    runtime = _FakeRuntime("native")

    result = send_opponent_final_reveal(
        runtime, records=[{"payload": {"step": 1, "nonce": "n", "intent": "truth"}}]
    )

    assert runtime.transport.calls == []
    assert result["verified_steps"] == 0


def test_play_opponent_round_threads_round_exchange_and_deadline_through_for_cop_v1(monkeypatch):
    # The lockstep fix depends on play_round_cop actually receiving the
    # real round_exchange/round_deadline_sec -- this call path had no
    # test at all before, exactly the kind of wiring gap that let the
    # loop silently race ahead unnoticed.
    captured = {}

    def fake_play_round_cop(
        step, turn_handler, turn_fsm, scent, trash_talk, round_exchange, transport,
        round_deadline_sec, strategy_deadline_sec, last_opponent_scent,
    ):
        captured["round_exchange"] = round_exchange
        captured["round_deadline_sec"] = round_deadline_sec
        captured["strategy_deadline_sec"] = strategy_deadline_sec
        return {"payload": {}}, {}, False

    monkeypatch.setattr(
        "thief_peer.interop.cop_opponent.play_round_cop", fake_play_round_cop
    )

    runtime = _FakeRuntime("cop_v1")
    runtime.turn_handler = object()
    runtime.turn_fsm = object()
    runtime.scent = object()
    runtime.trash_talk = object()
    runtime.round_exchange = object()
    runtime.round_deadline_sec = 12.5
    runtime.strategy_deadline_sec = 7.5
    runtime._last_opponent_scent = {}

    play_opponent_round(runtime, 3)

    assert captured["round_exchange"] is runtime.round_exchange
    assert captured["round_deadline_sec"] == 12.5
    assert captured["strategy_deadline_sec"] == 7.5
