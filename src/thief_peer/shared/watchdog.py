"""Watchdog (PRD_5 §2.3, §3): an independent, whole-system background check
verifying the main peer loop is still alive at all -- distinct from the
per-request Deadline Tracker (`infra/mcp_client.py`), which can't catch a
frozen main loop, since the code that would raise its own timeout is
itself what's hung (book Ch.8.4.2). The heartbeat *producer* side belongs
to `peer/runtime.py`, arriving in a later stage; this module is the
checker, built and unit-tested now (PRD_5 "Open items").
"""

import os
import time
from pathlib import Path

_STATE_PATH = Path("logs/watchdog_state.json")


def watchdog_check(last_heartbeat: float, timeout_sec: float) -> str:
    if time.time() - last_heartbeat > timeout_sec:
        persist_state()
        controlled_shutdown()
        return "SHUTDOWN"
    return "ALIVE"


def persist_state() -> None:
    """Write enough state to disk that a future run could diagnose (not
    necessarily resume) what the match was doing when it froze -- ties
    into Stage 7's logging, kept minimal here (PRD_5 §3)."""
    import json

    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(
        json.dumps({"event": "watchdog_shutdown", "timestamp": time.time()}),
        encoding="utf-8",
    )


def controlled_shutdown(exit_fn=None) -> None:
    """Actually end the frozen process -- book ch.8.4.2's own point is that
    the *main* thread is the one that's hung, and this function runs on
    the watchdog's own background thread (`peer/heartbeat_monitor.py::
    HeartbeatMonitor._loop`). Nothing on a genuinely frozen main thread
    will ever check a flag this function might set instead of exiting;
    `sys.exit()` only raises `SystemExit` in whichever thread calls it,
    which would do nothing to a frozen *different* thread either. A hard
    `os._exit()` from the watchdog thread is the only mechanism that
    reliably ends the process regardless of what the main thread is
    doing -- previously this printed a message and returned, leaving the
    frozen process running indefinitely with no real shutdown at all.
    `exit_fn` is injectable (real callers never override it) so tests can
    spy on this without actually terminating the test process."""
    print("[watchdog] controlled shutdown: heartbeat stale, stopping cleanly.")
    (exit_fn or os._exit)(1)
