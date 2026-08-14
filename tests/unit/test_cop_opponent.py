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
    run_opponent_handshake,
    send_opponent_final_reveal,
)
from thief_peer.report.report_writer import LeagueCounter


class _FakeAdapter:
    def __init__(self):
        self.final_reveal_received = threading.Event()


class _FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, name, payload, retryable=True):
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


class _NativeFakeRuntime:
    def __init__(self, results_dir):
        self.opponent_protocol = "native"
        self.config = object()
        self.transport = object()
        self.group_name = "Thief-Team"
        self.shared_config_path = None
        self.results_dir = results_dir


def test_run_opponent_handshake_declares_the_real_games_played_so_far_in_native_mode(
    tmp_path, monkeypatch
):
    # Rules 37/38: the native-mode initiator side must read the real
    # league counter, not always declare 0.
    results_dir = tmp_path / "results"
    LeagueCounter(results_dir / "league_counter.json").record_game("Cop-Team-Other")
    LeagueCounter(results_dir / "league_counter.json").record_game("Cop-Team-Other-2")
    runtime = _NativeFakeRuntime(results_dir)
    captured = {}

    def fake_run_handshake(config, transport, group_name, shared_config_path, games_played_so_far):
        captured["games_played_so_far"] = games_played_so_far
        return {"payload": {"group_name": "Cop-Team"}}

    monkeypatch.setattr("thief_peer.interop.cop_opponent.run_handshake", fake_run_handshake)

    opponent_group_name = run_opponent_handshake(runtime)

    assert captured["games_played_so_far"] == 2
    assert opponent_group_name == "Cop-Team"


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
