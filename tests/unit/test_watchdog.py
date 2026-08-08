"""shared/watchdog.py tests (PRD_5 §2.3, §3, §5). A second, independent
observer for a frozen main loop -- the failure mode a per-request Deadline
Tracker can't catch, since the code that would raise its own timeout is
itself what's hung (book Ch.8.4.2)."""

import time

from thief_peer.shared import watchdog


def test_watchdog_check_returns_alive_when_heartbeat_is_recent():
    result = watchdog.watchdog_check(last_heartbeat=time.time(), timeout_sec=60)
    assert result == "ALIVE"


def test_watchdog_check_returns_shutdown_when_heartbeat_is_stale(monkeypatch):
    # Pre-existing bug found in a later compliance re-audit: this test never
    # mocked persist_state()/controlled_shutdown(), so it silently wrote a
    # real logs/watchdog_state.json into the repo on every run since Stage 5
    # -- gitignored, so never a commit risk, but real local pollution that
    # went unnoticed until something started actually checking for it.
    monkeypatch.setattr(watchdog, "persist_state", lambda: None)
    monkeypatch.setattr(watchdog, "controlled_shutdown", lambda: None)
    stale_heartbeat = time.time() - 120
    result = watchdog.watchdog_check(last_heartbeat=stale_heartbeat, timeout_sec=60)
    assert result == "SHUTDOWN"


def test_watchdog_check_is_a_strict_boundary_not_off_by_one(monkeypatch):
    # Exactly at the threshold must not trip -- only *exceeding* it does
    # (PRD_5 §3: "if now - last_heartbeat > timeout_sec"). Also unmocked
    # for persist_state/controlled_shutdown until the same re-audit that
    # found the sibling test above -- same real-file-write bug.
    monkeypatch.setattr(watchdog, "persist_state", lambda: None)
    monkeypatch.setattr(watchdog, "controlled_shutdown", lambda: None)
    now = 1_000_000.0
    monkeypatch.setattr(watchdog.time, "time", lambda: now)
    assert watchdog.watchdog_check(last_heartbeat=now - 60, timeout_sec=60) == "ALIVE"
    assert watchdog.watchdog_check(last_heartbeat=now - 60.0001, timeout_sec=60) == "SHUTDOWN"


def test_watchdog_check_calls_persist_state_and_controlled_shutdown_exactly_once_on_shutdown(
    monkeypatch,
):
    persist_calls = []
    shutdown_calls = []
    monkeypatch.setattr(watchdog, "persist_state", lambda: persist_calls.append(1))
    monkeypatch.setattr(watchdog, "controlled_shutdown", lambda: shutdown_calls.append(1))

    stale_heartbeat = time.time() - 120
    watchdog.watchdog_check(last_heartbeat=stale_heartbeat, timeout_sec=60)

    assert len(persist_calls) == 1
    assert len(shutdown_calls) == 1


def test_watchdog_check_never_calls_persist_state_or_shutdown_when_alive(monkeypatch):
    persist_calls = []
    shutdown_calls = []
    monkeypatch.setattr(watchdog, "persist_state", lambda: persist_calls.append(1))
    monkeypatch.setattr(watchdog, "controlled_shutdown", lambda: shutdown_calls.append(1))

    watchdog.watchdog_check(last_heartbeat=time.time(), timeout_sec=60)

    assert persist_calls == []
    assert shutdown_calls == []


def test_persist_state_writes_a_diagnosable_file(tmp_path, monkeypatch):
    state_path = tmp_path / "watchdog_state.json"
    monkeypatch.setattr(watchdog, "_STATE_PATH", state_path)

    watchdog.persist_state()

    assert state_path.exists()
    content = state_path.read_text(encoding="utf-8")
    assert "timestamp" in content


def test_controlled_shutdown_runs_without_raising(capsys):
    watchdog.controlled_shutdown()
    captured = capsys.readouterr()
    assert "shutdown" in captured.out.lower()
