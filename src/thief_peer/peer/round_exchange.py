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

    def wait_for_commit(self, step: int, timeout: float) -> str:
        return self._wait_for(self._commits, step, timeout, "commit")

    def wait_for_reveal(self, step: int, timeout: float) -> dict:
        return self._wait_for(self._reveals, step, timeout, "reveal")

    def _wait_for(self, store: dict, step: int, timeout: float, kind: str):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if step in store:
                    return store[step]
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(
            f"No {kind} received for step {step} within {timeout}s"
        )
