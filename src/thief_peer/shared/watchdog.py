"""Watchdog (PRD_5 §2.3, §3): an independent, whole-system background check
verifying the main peer loop is still alive at all -- distinct from the
per-request Deadline Tracker (`infra/mcp_client.py`), which can't catch a
frozen main loop, since the code that would raise its own timeout is
itself what's hung (book Ch.8.4.2). The heartbeat *producer* side belongs
to `peer/runtime.py`, arriving in a later stage; this module is the
checker, built and unit-tested now (PRD_5 "Open items").
"""

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
    """Release the MCP server/client cleanly, close any open log handles --
    never a bare process kill (PRD_5 §3). Full resource release is wired
    once `PeerRuntime` owns real server/client handles (later stages); for
    now this is the single, named chokepoint every future stage extends."""
    print("[watchdog] controlled shutdown: heartbeat stale, stopping cleanly.")
