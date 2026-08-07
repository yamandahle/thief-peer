"""gui/* tests (PRD_7 §2.1-2.2, §5; PLAN.md ADR-8). The GUI-never-renders-
Cop-position guarantee is structural, not behavioral: PeerView simply has
no field an opponent position could occupy, checked here via dataclass
field introspection, not by trying to spot a rendered pixel."""

import dataclasses
import tkinter as tk

import pytest

from thief_peer.gui.board_view import BoardView, _heat_color
from thief_peer.gui.turn_banner import TurnBanner, banner_for_state
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


def test_peer_view_has_no_opponent_position_field_at_all():
    field_names = {f.name for f in dataclasses.fields(PeerView)}
    assert "own_position" in field_names
    assert "belief_matrix" in field_names
    assert not any("cop" in name.lower() for name in field_names)
    assert not any("opponent" in name.lower() and "position" in name.lower() for name in field_names)


def test_peer_view_is_frozen_so_a_position_cannot_be_bolted_on_later():
    view = PeerView(own_position=(2, 2), belief_matrix=[[1.0]], turn_state="COMPUTING_MOVE", step_count=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.own_position = (0, 0)


def test_banner_for_state_is_your_turn_only_during_computing_move():
    text, _color = banner_for_state("COMPUTING_MOVE")
    assert text == "YOUR TURN"


@pytest.mark.parametrize(
    "state", ["WAITING_FOR_OPPONENT", "COMMITTING", "AWAITING_REVEAL", "VERIFYING", "TECHNICAL_LOSS"]
)
def test_banner_for_state_is_locked_for_every_other_state(state):
    text, _color = banner_for_state(state)
    assert text == "LOCKED"


def test_banner_your_turn_and_locked_use_different_colors():
    _text1, color1 = banner_for_state("COMPUTING_MOVE")
    _text2, color2 = banner_for_state("WAITING_FOR_OPPONENT")
    assert color1 != color2


def test_heat_color_is_coldest_at_zero_and_warmest_at_the_max():
    cold = _heat_color(0.0, max_value=1.0)
    warm = _heat_color(1.0, max_value=1.0)
    assert cold != warm


def test_heat_color_handles_an_all_zero_matrix_without_dividing_by_zero():
    color = _heat_color(0.0, max_value=0.0)
    assert isinstance(color, str) and color.startswith("#")


def test_board_view_render_does_not_raise_and_draws_the_own_position(hidden_root):
    view = PeerView(
        own_position=(1, 1),
        belief_matrix=[[0.1, 0.2], [0.3, 0.4]],
        turn_state="COMPUTING_MOVE",
        step_count=3,
    )
    board_view = BoardView(hidden_root)
    board_view.render(view)

    items = board_view.canvas.find_all()
    assert len(items) > 0


def test_turn_banner_render_updates_label_text(hidden_root):
    banner = TurnBanner(hidden_root)
    banner.render("COMPUTING_MOVE")
    assert banner.label.cget("text") == "YOUR TURN"

    banner.render("VERIFYING")
    assert banner.label.cget("text") == "LOCKED"


def test_peer_window_render_wires_board_view_and_turn_banner(hidden_root):
    window = PeerWindow(root=hidden_root)
    view = PeerView(own_position=(0, 0), belief_matrix=[[1.0]], turn_state="COMPUTING_MOVE", step_count=0)

    window.render(view)  # must not raise

    assert window.turn_banner.label.cget("text") == "YOUR TURN"
