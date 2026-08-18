"""RoundExchange (PRD_8 §3): a thread-safe mailbox bridging the MCP server
thread (writer, on inbound commit_move/reveal_move calls) and the main
PeerRuntime loop thread (reader). Lock + bounded poll loop, matching the
existing wait_until_ready pattern in infra/mcp_server.py rather than
introducing a second concurrency idiom for the same kind of cross-thread
wait. "A missed deadline is a failure, not patience" (book Ch.8) -- a
step whose commit/reveal never arrives raises DeadlineExceededError instead
of blocking forever.
"""

import threading
import time

from thief_peer.exceptions import DeadlineExceededError


class RoundExchange:
    def __init__(self, poll_interval: float = 0.05):
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._commits: dict[int, str] = {}
        self._reveals: dict[int, dict] = {}

    def record_commit(self, step: int, h_commit: str) -> None:
        with self._lock:
            self._commits[step] = h_commit

    def record_reveal(self, step: int, message: dict) -> None:
        with self._lock:
            self._reveals[step] = message

    def wait_for_commit(self, step: int, timeout: float, interrupt=None) -> str:
        return self._wait_for(self._commits, step, timeout, "commit", interrupt)

    def wait_for_reveal(self, step: int, timeout: float, interrupt=None) -> dict | None:
        return self._wait_for(self._reveals, step, timeout, "reveal", interrupt)

    def _wait_for(self, store: dict, step: int, timeout: float, kind: str, interrupt=None):
        """`interrupt` is an optional `threading.Event` (e.g. `PeerRuntime.
        _round_wakeup`, set the instant a confirmed capture lands on the
        MCP server's own thread) checked every poll tick -- found via a
        real live match where a capture confirmed mid-wait for the *next*
        round otherwise ran out the full `timeout` before the caller's own
        round-boundary check ever got a chance to notice, producing a false
        technical_loss instead of a clean, immediate match end. Returns
        `None` (never raises) on interrupt -- distinct from a genuine
        missing message, which the caller couldn't otherwise tell apart
        from "the opponent has legitimately ended the match already"."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if interrupt is not None and interrupt.is_set():
                return None
            with self._lock:
                if step in store:
                    return store[step]
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(
            f"No {kind} received for step {step} within {timeout}s"
        )
