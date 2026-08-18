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
    run_opponent_handshake,
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


def test_send_opponent_final_reveal_survives_an_unreachable_peer_instead_of_crashing():
    # docs/todoFIXMCP.md: this call was previously unguarded -- if the
    # round loop already ended in a technical loss because the peer
    # became unreachable, this send can hit that same unreachable peer,
    # and an uncaught exception here would crash the whole match-report
    # sequence (no report at all) instead of the honest "not evaluated"
    # this function already returns for native-protocol opponents.
    from thief_peer.exceptions import TransportError

    class _UnreachableTransport:
        def call(self, name, payload):
            raise TransportError("could not reach opponent")

    runtime = _FakeRuntime("cop_v1")
    runtime.transport = _UnreachableTransport()

    result = send_opponent_final_reveal(
        runtime, records=[{"payload": {"step": 1, "nonce": "n", "intent": True}}]
    )

    assert result == {
        "passed": False,
        "verified_steps": 0,
        "failed_steps": [],
        "failed_capture_claims": [],
        "evaluated": False,
    }


def test_send_opponent_final_reveal_does_nothing_in_native_mode():
    runtime = _FakeRuntime("native")

    result = send_opponent_final_reveal(
        runtime, records=[{"payload": {"step": 1, "nonce": "n", "intent": "truth"}}]
    )

    assert runtime.transport.calls == []
    assert result["verified_steps"] == 0


def test_run_opponent_handshake_extracts_group_name_and_commit_hash_for_cop_v1(monkeypatch):
    # Both wire shapes already carry a git commit hash in their Step-0
    # declaration -- this just wasn't threaded past the handshake call
    # before, so `finalize_match`'s report had no way to populate the
    # result artifact's `github_commit` field.
    monkeypatch.setattr(
        "thief_peer.interop.cop_opponent.cop_step0_handshake",
        lambda *a, **k: {"declaration": {"group_name": "Cop-Team", "code_commit_hash": "abc123"}},
    )
    runtime = _FakeRuntime("cop_v1")
    runtime.config = object()
    runtime.group_name = "Thief-Team"
    runtime.sub_game_number = 1
    runtime.shared_config_path = "shared.toml"
    runtime.repos = {}

    result = run_opponent_handshake(runtime)

    assert result == {"group_name": "Cop-Team", "github_commit": "abc123"}


def test_run_opponent_handshake_extracts_group_name_and_commit_hash_natively(monkeypatch):
    monkeypatch.setattr(
        "thief_peer.interop.cop_opponent.run_handshake",
        lambda *a, **k: {"payload": {"group_name": "Thief-Team-B", "github_commit_hash": "def456"}},
    )
    runtime = _FakeRuntime("native")
    runtime.config = object()
    runtime.group_name = "Thief-Team-A"
    runtime.shared_config_path = "shared.toml"

    result = run_opponent_handshake(runtime)

    assert result == {"group_name": "Thief-Team-B", "github_commit": "def456"}


def test_play_opponent_round_threads_round_exchange_and_deadline_through_for_cop_v1(monkeypatch):
    # The lockstep fix depends on play_round_cop actually receiving the
    # real round_exchange/round_deadline_sec -- this call path had no
    # test at all before, exactly the kind of wiring gap that let the
    # loop silently race ahead unnoticed.
    captured = {}

    def fake_play_round_cop(
        step, turn_handler, turn_fsm, scent, trash_talk, round_exchange, transport,
        round_deadline_sec, strategy_deadline_sec, last_opponent_scent, round_wakeup,
    ):
        captured["round_exchange"] = round_exchange
        captured["round_deadline_sec"] = round_deadline_sec
        captured["strategy_deadline_sec"] = strategy_deadline_sec
        captured["round_wakeup"] = round_wakeup
        return {"payload": {}}, {}, False, None

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
    runtime._round_wakeup = object()

    play_opponent_round(runtime, 3)

    assert captured["round_exchange"] is runtime.round_exchange
    assert captured["round_deadline_sec"] == 12.5
    assert captured["strategy_deadline_sec"] == 7.5
    assert captured["round_wakeup"] is runtime._round_wakeup
