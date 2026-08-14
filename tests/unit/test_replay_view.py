"""gui/replay_view.py tests (PRD_7 §2.3, §3, §5). verify_step must reuse
domain/crypto.py's exact functions, never a separate/duplicated
verification routine -- any mismatch, even a single-byte change to past
data, flips the whole match to TAMPERED with no appeal."""

import inspect
import tkinter as tk

import pytest

from thief_peer.domain.crypto import CommitReveal
from thief_peer.gui.replay_view import ReplayView, _first_tampered_index, replay, verify_step


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


def test_first_tampered_index_is_none_on_a_fully_clean_log():
    assert _first_tampered_index(_clean_log(4)) is None


def test_first_tampered_index_finds_the_earliest_one_not_just_any():
    log = _clean_log(5)
    log[3]["payload"]["state"] = "tampered"
    log[1]["payload"]["state"] = "also-tampered"
    assert _first_tampered_index(log) == 1


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


def test_replay_view_forward_halts_at_the_first_tampered_step_no_appeal(hidden_root):
    # Book ch.7.4: "disqualified on the first mismatch, no appeal" -- step 2
    # is individually clean on its own, but Forward must not be able to
    # reach it once step 1 is tampered; that would misleadingly read as
    # "it recovered."
    log = _clean_log(3)
    log[1]["payload"]["move"] = "S"
    view = ReplayView(hidden_root, log)

    view.step_forward()  # step 0 -> step 1 (the tampered step)
    assert view.index == 1
    view.step_forward()  # blocked -- must not reach step 2
    assert view.index == 1
    view.step_forward()  # still blocked, repeated clicks don't creep forward
    assert view.index == 1


def test_replay_view_forward_still_works_normally_on_a_fully_clean_log(hidden_root):
    view = ReplayView(hidden_root, _clean_log(3))
    view.step_forward()
    view.step_forward()
    assert view.index == 2  # unrestricted when nothing is tampered


def test_replay_view_shows_the_disqualified_label_at_the_tampered_step(hidden_root):
    log = _clean_log(3)
    log[1]["payload"]["move"] = "S"
    view = ReplayView(hidden_root, log)

    view.step_forward()

    assert "disqualified" in view.label.cget("text").lower()


def test_replay_view_back_is_never_restricted_by_a_tampered_step_ahead(hidden_root):
    # Reviewing the clean history before the tamper point is exactly what
    # establishes where it happened -- only Forward past it is blocked.
    log = _clean_log(3)
    log[1]["payload"]["move"] = "S"
    view = ReplayView(hidden_root, log)

    view.step_forward()  # at the tampered step (index 1)
    view.step_back()
    assert view.index == 0
    assert "Verified OK" in view.label.cget("text")


def test_replay_view_tamper_at_the_very_first_step_blocks_all_forward_movement(hidden_root):
    log = _clean_log(3)
    log[0]["payload"]["move"] = "S"
    view = ReplayView(hidden_root, log)

    assert view.index == 0
    assert "TAMPERED" in view.label.cget("text")
    view.step_forward()
    assert view.index == 0  # never left step 0


def test_replay_view_handles_an_empty_log_without_raising(hidden_root):
    view = ReplayView(hidden_root, [])
    assert view.label.cget("text") == "(empty log)"
