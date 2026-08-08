"""peer/heartbeat_monitor.py tests (rule 7 fix). HeartbeatMonitor is the
"producer" side shared/watchdog.py's own docstring said belonged to
peer/runtime.py "in a later stage" -- never actually built until this fix,
found the same compliance re-audit surfaced the other Stage-8 gaps: a
background daemon thread polling shared/watchdog.py's watchdog_check
against a heartbeat PeerRuntime's own round loop updates."""

import time

from thief_peer.peer.heartbeat_monitor import HeartbeatMonitor
from thief_peer.shared import watchdog


def _stub_out_real_shutdown_side_effects(monkeypatch):
    # watchdog_check's own persist_state()/controlled_shutdown() write a
    # real file and print a message -- matching test_watchdog.py's own
    # pattern, stubbed here so this test doesn't leave a stray
    # logs/watchdog_state.json in the repo directory.
    monkeypatch.setattr(watchdog, "persist_state", lambda: None)
    monkeypatch.setattr(watchdog, "controlled_shutdown", lambda: None)


def test_starts_alive_and_stays_alive_while_beat_keeps_getting_called(monkeypatch):
    # Defensively stubbed even though this test doesn't expect to trigger --
    # a generous but not infinite timeout_sec margin (10x the sleep budget,
    # not 4x) is what actually prevents the flake under a slow/loaded full
    # suite run; the stub is a second line of defense against ever writing
    # a real logs/watchdog_state.json if timing is unlucky anyway.
    _stub_out_real_shutdown_side_effects(monkeypatch)
    monitor = HeartbeatMonitor(timeout_sec=5.0, poll_interval_sec=0.05)

    thread = monitor.start()
    try:
        for _ in range(5):
            time.sleep(0.05)
            monitor.beat()
        assert monitor.triggered is False
    finally:
        monitor.stop()
        thread.join(timeout=1.0)


def test_triggers_when_beat_stops_being_called(monkeypatch):
    _stub_out_real_shutdown_side_effects(monkeypatch)
    monitor = HeartbeatMonitor(timeout_sec=0.1, poll_interval_sec=0.02)
    monitor.last_heartbeat = time.time() - 10  # already stale before starting

    thread = monitor.start()
    thread.join(timeout=1.0)

    assert monitor.triggered is True


def test_stop_ends_the_background_thread_cleanly():
    monitor = HeartbeatMonitor(timeout_sec=60, poll_interval_sec=0.02)

    thread = monitor.start()
    monitor.stop()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert monitor.triggered is False


def test_beat_updates_the_recorded_heartbeat_time():
    monitor = HeartbeatMonitor(timeout_sec=60)
    monitor.last_heartbeat = 0.0

    monitor.beat()

    assert monitor.last_heartbeat > 0.0
