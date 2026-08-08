"""HeartbeatMonitor: the heartbeat *producer* + background checker pairing
`shared/watchdog.py`'s own docstring said belonged to `peer/runtime.py`
"in a later stage" (PRD_5 "Open items") -- never actually built until this
fix (rule 7), found in the same compliance re-audit as the other Stage-8
gaps. Runs `watchdog_check` on a background daemon thread, polling a
heartbeat timestamp `PeerRuntime`'s own round loop updates via `beat()`
after every round -- a main-loop freeze (not caught by the per-request
Deadline Tracker, since the code that would raise its own timeout is
itself what's hung, book Ch.8.4.2) leaves the heartbeat stale, which this
thread alone can detect. Split out of `peer/runtime.py` to stay under this
codebase's file-length convention.
"""

import threading
import time

from thief_peer.shared.watchdog import watchdog_check


class HeartbeatMonitor:
    def __init__(self, timeout_sec: float, poll_interval_sec: float = 1.0):
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.last_heartbeat = time.time()
        self.triggered = False
        self._stop = False

    def beat(self) -> None:
        self.last_heartbeat = time.time()

    def stop(self) -> None:
        self._stop = True

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()
        return thread

    def _loop(self) -> None:
        while not self._stop:
            if watchdog_check(self.last_heartbeat, self.timeout_sec) == "SHUTDOWN":
                self.triggered = True
                return
            time.sleep(self.poll_interval_sec)
