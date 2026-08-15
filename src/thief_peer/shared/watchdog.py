"""Watchdog (PRD_5 §2.3, §3): an independent, whole-system background check
verifying the main peer loop is still alive at all -- distinct from the
per-request Deadline Tracker (`infra/mcp_client.py`), which can't catch a
frozen main loop, since the code that would raise its own timeout is
itself what's hung (book Ch.8.4.2). The heartbeat *producer* side belongs
to `peer/runtime.py`, arriving in a later stage; this module is the
checker, built and unit-tested now (PRD_5 "Open items").
"""

import os
import sys
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


def controlled_shutdown() -> None:
    """Release the MCP server/client cleanly, close any open log handles,
    then genuinely terminate the process (book Ch.8.4.2's own code sketch:
    "release MCP connections, close logs") -- never a bare print statement
    masquerading as a shutdown. `os._exit(1)` terminates immediately,
    which already releases every open socket/file handle via normal OS
    process teardown -- deliberately the same shape as a hard process
    kill after state is safely persisted, not an attempt at a graceful
    in-Python socket-close sequence from a background thread (which the
    watchdog thread, running independently of whatever froze the main
    loop, has no reliable way to drive)."""
    print("[watchdog] controlled shutdown: heartbeat stale, stopping cleanly.")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)
