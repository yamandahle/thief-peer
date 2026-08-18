"""interop/cop_server_tools.py tests: CopContextAdapter translates her real
wire calls into this repo's existing context.handle_* methods -- proven
against a spy context (unit level) and, for the tool-registration wiring
itself, a real live FastMCP round trip using this repo's own outbound
cop_turn_sender functions as the caller (both halves of this repo's own
adapter talking to each other over real sockets, not a real Cop process,
but real proof the FastMCP wiring/shapes are actually correct)."""

import threading

import pytest
from fastmcp import FastMCP

from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.server_lifecycle import wait_until_ready
from thief_peer.interop.cop_server_registration import register_cop_tools
from thief_peer.interop.cop_server_tools import CopContextAdapter
from thief_peer.interop.cop_turn_sender import (
    cop_request_scent_map,
    cop_send_barrier_declaration,
    cop_send_commit,
    cop_send_final_reveal,
    cop_send_reveal,
)


class _State:
    def __init__(self, position=(0, 0)):
        self.position = position  # (row, col), matching domain/board.py's Cell


class _FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, name, payload):
        self.calls.append((name, payload))
        return {"acknowledged": True}


class _Cfg:
    def require(self, key):
        return {
            "board_and_agents.cop_start": [0, 0],
            "board_and_agents.grid_size": 7,
        }[key]


class _SpyContext:
    def __init__(self, position=(0, 0)):
        self.calls = []
        self.config = _Cfg()
        self.group_name = "Thief-Team"
        self.repos = {"cop": "x", "thief": "y"}
        self.state = _State(position)
        self.transport = _FakeTransport()
        self._round_wakeup = threading.Event()

        class _Scent:
            def snapshot(self):
                return {"4,3": 0.62}

        self.scent = _Scent()

    def handle_commit_move(self, payload):
        self.calls.append(("commit_move", payload))
        return {"ok": True}

    def handle_reveal_move(self, payload):
        self.calls.append(("reveal_move", payload))
        return {"ok": True}

    def handle_receive_barrier_declaration(self, payload):
        self.calls.append(("receive_barrier_declaration", payload))
        return {"ok": True}


def test_handle_receive_commit_assigns_sequential_steps_and_delegates():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_commit("hash-0")
    adapter.handle_receive_commit("hash-1")

    assert context.calls == [
        ("commit_move", {"step": 1, "h_commit": "hash-0"}),
        ("commit_move", {"step": 2, "h_commit": "hash-1"}),
    ]


def test_handle_receive_commit_ignores_a_retried_duplicate_of_the_pending_commit():
    # docs/todoFIXMCP.md #2: an exact repeat of the still-unrevealed
    # commit's hash is a retry-echo, not a new round -- must not
    # double-advance the step counter or record a second commit_move.
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    first = adapter.handle_receive_commit("hash-0")
    second = adapter.handle_receive_commit("hash-0")  # retried duplicate

    assert context.calls == [("commit_move", {"step": 1, "h_commit": "hash-0"})]
    assert first == {"acknowledged": True}
    assert second == {"acknowledged": True}
    assert len(adapter.peer_trace.entries) == 1  # not double-recorded either
    assert adapter.peer_trace.entries[1].h_commit == "hash-0"


def test_handle_receive_commit_accepts_the_same_hash_again_once_a_new_round_starts():
    # A repeat hash is only a duplicate-echo while its own reveal is still
    # pending -- once revealed, the guard must not falsely suppress an
    # unrelated later round (even one that coincidentally shares content).
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_commit("hash-0")
    adapter.handle_receive_reveal({"type": "move", "direction": "N"}, "cold")
    adapter.handle_receive_commit("hash-0")  # not a duplicate -- new round

    assert context.calls == [
        ("commit_move", {"step": 1, "h_commit": "hash-0"}),
        ("reveal_move", {"step": 1, "sender": "cop", "hint": "cold", "scent_grid": {}, "move": "N", "intent": "truth"}),
        ("commit_move", {"step": 2, "h_commit": "hash-0"}),
    ]


def test_handle_receive_reveal_ignores_a_retried_duplicate_for_the_current_step():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")
    adapter.handle_receive_commit("hash-0")

    first = adapter.handle_receive_reveal({"type": "move", "direction": "N"}, "cold")
    second = adapter.handle_receive_reveal({"type": "move", "direction": "N"}, "cold")  # retried

    reveal_calls = [c for c in context.calls if c[0] == "reveal_move"]
    assert len(reveal_calls) == 1
    assert first == second == {"accepted": True, "word_count": 1}
    assert adapter.peer_trace.entries[1].hint_text == "cold"  # not double-recorded either


def test_handle_receive_reveal_accepts_a_legitimately_repeated_move_in_the_next_round():
    # move/hint_text content (unlike h_commit) can legitimately repeat --
    # the guard must key off step-boundary, not content equality.
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")
    adapter.handle_receive_commit("hash-0")
    adapter.handle_receive_reveal({"type": "move", "direction": "STAY"}, "cold")
    adapter.handle_receive_commit("hash-1")

    adapter.handle_receive_reveal({"type": "move", "direction": "STAY"}, "cold")  # same content, new round

    reveal_calls = [c for c in context.calls if c[0] == "reveal_move"]
    assert len(reveal_calls) == 2
    assert reveal_calls[1] == (
        "reveal_move",
        {"step": 2, "sender": "cop", "hint": "cold", "scent_grid": {}, "move": "STAY", "intent": "truth"},
    )


def test_handle_receive_reveal_translates_her_typed_move_into_our_direction_string():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    result = adapter.handle_receive_reveal({"type": "move", "direction": "N"}, "cold")

    assert context.calls == [
        ("reveal_move", {"step": 1, "sender": "cop", "hint": "cold", "scent_grid": {}, "move": "N", "intent": "truth"})
    ]
    assert result == {"accepted": True, "word_count": 1}


def test_handle_receive_commit_accepts_and_logs_peer_deadline_metadata(capsys):
    # A real Cop client now attaches sent_at/deadline_at (PRD_15's Deadline
    # Tracker, Ch.8.4) to her receive_commit/receive_reveal calls -- rule 9
    # means this is observability-only, logged but never trusted to affect
    # our own commit_move handling.
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_commit("hash-0", sent_at=1000.0, deadline_at=1030.0)

    assert context.calls == [("commit_move", {"step": 1, "h_commit": "hash-0"})]
    assert "sent_at=1000.0" in capsys.readouterr().out


def test_handle_receive_commit_without_deadline_metadata_logs_nothing(capsys):
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_commit("hash-0")

    assert capsys.readouterr().out == ""


def test_handle_receive_reveal_accepts_and_logs_peer_deadline_metadata(capsys):
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_reveal(
        {"type": "move", "direction": "N"}, "cold", sent_at=2000.0, deadline_at=2030.0
    )

    assert context.calls == [
        ("reveal_move", {"step": 1, "sender": "cop", "hint": "cold", "scent_grid": {}, "move": "N", "intent": "truth"})
    ]
    assert "deadline_at=2030.0" in capsys.readouterr().out


def test_handle_share_scent_map_serializes_the_live_scent_field():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    assert adapter.handle_share_scent_map() == {"cells": [[3, 4, 0.62]]}


def test_handle_receive_barrier_declaration_swaps_col_row_into_our_row_col_payload():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_barrier_declaration(col=5, row=2)

    assert context.calls == [("receive_barrier_declaration", {"row": 2, "col": 5})]


def test_handle_receive_barrier_declaration_acks_in_her_shape_not_the_native_one():
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")

    result = adapter.handle_receive_barrier_declaration(col=5, row=2)

    assert result == {"acknowledged": True}


def test_handle_receive_capture_claim_acks_immediately_then_confirms_a_real_capture():
    context = _SpyContext(position=(2, 5))  # actually standing at row=2, col=5
    adapter = CopContextAdapter(context, shared_config_path="unused")

    result = adapter.handle_receive_capture_claim(
        thief_col=5, thief_row=2, cop_col=5, cop_row=2, claimed_at_step=9
    )

    assert result == {"acknowledged": True}
    assert context.transport.calls == [
        ("receive_capture_response", {"confirmed": True, "true_thief_col": 5, "true_thief_row": 2})
    ]
    claim = adapter.peer_trace.capture_claims[-1]
    assert claim.claimed_at_step == 9
    assert (claim.thief_row, claim.thief_col) == (2, 5)
    assert (claim.cop_row, claim.cop_col) == (2, 5)
    assert claim.confirmed is True
    # Rule 47 (direct-landing capture): unlike a barrier capture, nothing
    # else ever tells the main loop to stop for this capture mode -- a
    # confirmed claim must flag it directly on the runtime, or the loop
    # advances to a step the Cop (who already correctly ended her match)
    # will never send a reveal for, and hangs on wait_for_reveal forever.
    assert context._captured_by_landing is True
    # And _round_wakeup must fire too, or a wait already in progress for
    # the *current* round (not just a future one the top-of-loop check
    # would catch) still runs out its full deadline before noticing --
    # the exact false-technical_loss bug a real live match hit.
    assert context._round_wakeup.is_set()


def test_handle_receive_capture_claim_denies_and_reveals_true_position_when_wrong():
    context = _SpyContext(position=(9, 9))  # actually standing elsewhere
    context._captured_by_landing = False
    adapter = CopContextAdapter(context, shared_config_path="unused")

    adapter.handle_receive_capture_claim(
        thief_col=5, thief_row=2, cop_col=5, cop_row=2, claimed_at_step=9
    )

    assert context.transport.calls == [
        ("receive_capture_response", {"confirmed": False, "true_thief_col": 9, "true_thief_row": 9})
    ]
    assert context._captured_by_landing is False
    assert not context._round_wakeup.is_set()
    assert adapter.peer_trace.capture_claims[-1].confirmed is False


def test_handle_receive_capture_response_records_her_verdict():
    adapter = CopContextAdapter(_SpyContext(), shared_config_path="unused")

    result = adapter.handle_receive_capture_response(
        confirmed=True, true_thief_col=3, true_thief_row=4
    )

    assert result == {"acknowledged": True}
    assert adapter.peer_trace.capture_responses == [
        {"confirmed": True, "true_thief_row": 4, "true_thief_col": 3}
    ]


def test_handle_receive_final_reveal_audits_peer_and_acks():
    # Ch.5.3.2 + rules 19/36: Final Reveal triggers peer audit, not ack-only.
    adapter = CopContextAdapter(_SpyContext(position=(2, 5)), shared_config_path="unused")
    adapter.peer_trace.record_commit("deadbeef")
    adapter.peer_trace.record_reveal({"type": "move", "direction": "E"}, "hint")

    result = adapter.handle_receive_final_reveal({"1": "n" * 32}, {"1": True})

    assert result["acknowledged"] is True
    assert "passed" in result
    assert adapter.final_reveal_received.is_set()
    assert adapter.opponent_audit["evaluated"] is True


def test_handle_receive_final_reveal_acks_when_empty():
    adapter = CopContextAdapter(_SpyContext(), shared_config_path="unused")
    assert adapter.handle_receive_final_reveal({}, {})["acknowledged"] is True



@pytest.fixture
def live_server_with_cop_adapter(free_tcp_port):
    context = _SpyContext()
    adapter = CopContextAdapter(context, shared_config_path="unused")
    mcp = FastMCP(name="thief-peer-cop-adapter")
    register_cop_tools(mcp, adapter)
    thread = threading.Thread(
        target=mcp.run,
        kwargs={
            "transport": "http",
            "host": "127.0.0.1",
            "port": free_tcp_port,
            "show_banner": False,
            "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    wait_until_ready(free_tcp_port)
    yield free_tcp_port, context


def test_cop_send_commit_and_cop_send_reveal_actually_land_on_the_registered_server(
    live_server_with_cop_adapter,
):
    port, context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    cop_send_commit(transport, "hash-0")
    cop_send_reveal(transport, "N", "cold")

    assert context.calls == [
        ("commit_move", {"step": 1, "h_commit": "hash-0"}),
        ("reveal_move", {"step": 1, "sender": "cop", "hint": "cold", "scent_grid": {}, "move": "N", "intent": "truth"}),
    ]


def test_cop_request_scent_map_round_trips_over_a_real_socket(live_server_with_cop_adapter):
    port, _context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = cop_request_scent_map(transport)

    assert result == {"4,3": 0.62}


def test_cop_send_barrier_declaration_lands_with_row_col_swapped_back(live_server_with_cop_adapter):
    port, context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    cop_send_barrier_declaration(transport, row=2, col=5)

    assert context.calls == [("receive_barrier_declaration", {"row": 2, "col": 5})]


def test_cop_send_final_reveal_lands_on_the_registered_server(live_server_with_cop_adapter):
    port, _context = live_server_with_cop_adapter
    transport = McpTransport(f"http://127.0.0.1:{port}/mcp")

    result = cop_send_final_reveal(transport, {"0": "nonce"}, {"0": True})

    assert result["acknowledged"] is True
    assert "passed" in result  # rules 19/36 audit summary rides on the ack

