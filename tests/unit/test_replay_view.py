"""gui/replay_view.py tests (PRD_7 §2.3, §3, §5). verify_step must reuse
domain/crypto.py's exact functions, never a separate/duplicated
verification routine -- any mismatch, even a single-byte change to past
data, flips the whole match to TAMPERED with no appeal."""

import inspect
import tkinter as tk

import pytest

from thief_peer.domain.crypto import CommitReveal
from thief_peer.gui.replay_view import ReplayView, replay, verify_step


def _clean_log(n: int) -> list[dict]:
    records = []
    for i in range(n):
        payload = {"state": f"s{i}", "move": "N", "intent": "truth"}
        sealed = CommitReveal.seal(payload)
        records.append({"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]})
    return records


def test_verify_step_returns_verified_ok_for_a_clean_step():
    entry = _clean_log(1)[0]
    assert verify_step(entry) == "Verified OK"


def test_verify_step_returns_tampered_for_a_corrupted_step():
    entry = _clean_log(1)[0]
    entry["payload"]["move"] = "S"
    assert verify_step(entry) == "TAMPERED"


def test_verify_step_reuses_commitreveal_verify_not_a_duplicated_routine():
    import thief_peer.gui.replay_view as replay_view_module

    source = inspect.getsource(replay_view_module.verify_step)
    assert "CommitReveal.verify" in source
    assert "hashlib" not in inspect.getsource(replay_view_module)


def test_replay_returns_verified_ok_for_a_fully_clean_log():
    assert replay(_clean_log(4)) == "Verified OK"


def test_replay_returns_tampered_on_the_first_failure():
    log = _clean_log(4)
    log[2]["payload"]["state"] = "tampered-state"
    assert replay(log) == "TAMPERED"


def test_replay_on_an_empty_log_returns_verified_ok_trivially():
    assert replay([]) == "Verified OK"


@pytest.fixture
def hidden_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tkinter in this environment")
    root.withdraw()
    yield root
    root.destroy()


def test_replay_view_starts_at_step_zero_and_shows_verified_ok(hidden_root):
    view = ReplayView(hidden_root, _clean_log(3))
    assert view.index == 0
    assert "Verified OK" in view.label.cget("text")


def test_replay_view_steps_forward_and_back(hidden_root):
    view = ReplayView(hidden_root, _clean_log(3))
    view.step_forward()
    assert view.index == 1
    view.step_forward()
    assert view.index == 2
    view.step_forward()  # already at the last step -- must not overrun
    assert view.index == 2

    view.step_back()
    assert view.index == 1
    view.step_back()
    view.step_back()  # already at the first step -- must not underrun
    assert view.index == 0


def test_replay_view_flags_tampered_at_the_corrupted_step(hidden_root):
    log = _clean_log(3)
    log[1]["payload"]["move"] = "S"
    view = ReplayView(hidden_root, log)

    view.step_forward()  # now at the tampered step
    assert "TAMPERED" in view.label.cget("text")

    view.step_forward()  # step 2 was never touched, still clean on its own
    assert "Verified OK" in view.label.cget("text")


def test_replay_view_handles_an_empty_log_without_raising(hidden_root):
    view = ReplayView(hidden_root, [])
    assert view.label.cget("text") == "(empty log)"
