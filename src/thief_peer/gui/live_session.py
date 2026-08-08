"""LiveSession: wires a running PeerRuntime to a PeerWindow -- a gap left
over from PRD_7 (built the GUI) and PRD_8 (built PeerRuntime.view()), since
neither stage actually connected the two. PeerRuntime.run() blocks for the
whole match and Tkinter's mainloop() must own the main thread, so the match
runs on a background daemon thread while the window polls
PeerRuntime.view() on a Tk `.after()` timer -- the standard safe pattern for
combining Tkinter with background work (Tkinter widgets are not safe to
touch from a non-main thread, so the match thread never touches `window`
directly, only `runtime`).
"""

import threading
import tkinter as tk


def refresh_from_runtime(window, runtime) -> None:
    """One poll tick, isolated from the scheduling loop below so it's
    directly testable without a real Tk mainloop or a real match thread."""
    window.render(runtime.view())


class LiveSession:
    def __init__(self, runtime, window, poll_interval_ms: int = 200):
        self._runtime = runtime
        self._window = window
        self._poll_interval_ms = poll_interval_ms
        self.match_result: dict | None = None
        self._match_thread = threading.Thread(target=self._run_match, daemon=True)

    def start(self) -> None:
        """Blocks until the match is fully finished, whether or not that
        happens before or after the window is closed. Closing the window
        early stops the display, not the match: the opponent is still
        waiting on this peer's next commit/reveal, and abandoning that
        mid-round would leave them hanging on their own deadline rather
        than a clean match end -- so the background thread always runs to
        completion, `match_result` is always populated by the time this
        returns, and a closed-early window just means the tail of the
        match ran headless."""
        self._match_thread.start()
        self._schedule_poll()
        self._window.run()
        self._match_thread.join()

    def _run_match(self) -> None:
        self.match_result = self._runtime.run()

    def _schedule_poll(self) -> None:
        try:
            refresh_from_runtime(self._window, self._runtime)
            self._window.root.after(self._poll_interval_ms, self._schedule_poll)
        except tk.TclError:
            pass  # window was closed mid-poll; stop rescheduling
