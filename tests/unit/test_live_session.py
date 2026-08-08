"""gui/live_session.py tests. `refresh_from_runtime` is exercised directly
(no thread/mainloop needed); `LiveSession` itself is exercised against a
real (hidden) Tk window, ending its own mainloop via `root.quit()` -- never
`root.destroy()`, which would conflict with the `hidden_root` fixture's own
teardown."""

import time
import tkinter as tk

import pytest

from thief_peer.gui.live_session import LiveSession, refresh_from_runtime
from thief_peer.gui.window import PeerView, PeerWindow


@pytest.fixture
def hidden_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tkinter in this environment")
    root.withdraw()
    yield root
    root.destroy()


class _StubRuntime:
    def __init__(self, result: dict):
        self.view_calls = 0
        self._result = result

    def view(self) -> PeerView:
        self.view_calls += 1
        return PeerView(
            own_position=(0, 0),
            belief_matrix=[[1.0]],
            turn_state="COMPUTING_MOVE",
            step_count=self.view_calls,
        )

    def run(self) -> dict:
        return self._result


def test_refresh_from_runtime_renders_the_runtimes_current_view(hidden_root):
    window = PeerWindow(root=hidden_root)
    runtime = _StubRuntime({"final_result": {"winner_group": "Thief-Team"}})

    refresh_from_runtime(window, runtime)

    assert runtime.view_calls == 1
    assert window.turn_banner.label.cget("text") == "YOUR TURN"


def test_live_session_polls_repeatedly_and_captures_the_match_result(hidden_root):
    runtime = _StubRuntime({"final_result": {"winner_group": "Thief-Team"}})
    window = PeerWindow(root=hidden_root)
    session = LiveSession(runtime, window, poll_interval_ms=10)

    hidden_root.after(150, hidden_root.quit)  # end mainloop without destroying the root
    session.start()

    assert runtime.view_calls > 1
    assert session.match_result == {"final_result": {"winner_group": "Thief-Team"}}


def test_live_session_waits_for_the_match_to_finish_even_if_the_window_closes_first(hidden_root):
    """Closing the window must not abandon an in-progress match -- the
    opponent is still waiting on this peer's next commit/reveal."""

    class _SlowRuntime(_StubRuntime):
        def run(self) -> dict:
            time.sleep(0.2)
            return self._result

    runtime = _SlowRuntime({"final_result": {"winner_group": "Thief-Team"}})
    window = PeerWindow(root=hidden_root)
    session = LiveSession(runtime, window, poll_interval_ms=10)

    hidden_root.after(20, hidden_root.quit)  # window closes long before the match finishes
    start = time.monotonic()
    session.start()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.2, "start() returned before the match thread actually finished"
    assert session.match_result == {"final_result": {"winner_group": "Thief-Team"}}


def test_live_session_stops_rescheduling_gracefully_once_the_window_is_gone():
    # A throwaway root this test destroys itself -- deliberately not the
    # shared `hidden_root` fixture, whose own teardown also calls destroy()
    # and would double-destroy if this test used it instead.
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tkinter in this environment")
    root.withdraw()

    runtime = _StubRuntime({"final_result": {}})
    window = PeerWindow(root=root)
    session = LiveSession(runtime, window, poll_interval_ms=10)

    root.destroy()  # simulate the window already being closed

    session._schedule_poll()  # must not raise despite the destroyed root
