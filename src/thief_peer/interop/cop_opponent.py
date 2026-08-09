"""Opponent-protocol dispatch for `PeerRuntime`: routes handshake/round-loop
calls to either the native Thief vocabulary or the Cop interop adapter,
based on `network.opponent_protocol` in config ("native", the default, or
"cop_v1"). Free functions taking `runtime` explicitly, matching this
codebase's existing preference (`peer/handshake.py`, `peer/round_loop.py`)
for injectable collaborators over deep object coupling -- kept out of
`peer/runtime.py` itself, which is already at this project's 150-line cap.

This module is the intended extension point for onboarding a *different*
future league opponent (rule 31 requires playing several distinct teams,
not just this one paired Cop): add one new `interop/<team>_v1/`-style
adapter package mirroring `cop_v1`'s shape, then one more branch in each of
the functions below. `peer/runtime.py`, `peer/round_loop.py`, and
`peer/match_end.py`'s core logic never need to change for that -- only this
file grows. A new, uncoordinated opponent that never registers here still
gets `"native"`'s default behavior, which speaks only the book's own
baseline wire shapes/tool names -- no opponent is ever required to adopt
this repo's own extensions (e.g. the 7-field Commit-Reveal envelope, see
`peer/sealing.py`) just to complete a match.
"""

import time

from thief_peer.interop.cop_handshake import cop_step0_handshake
from thief_peer.interop.cop_round_loop import play_round_cop
from thief_peer.interop.cop_server_registration import register_cop_tools
from thief_peer.interop.cop_server_tools import CopContextAdapter
from thief_peer.interop.cop_turn_sender import cop_send_final_reveal
from thief_peer.interop.cop_wire import build_cop_final_reveal_payload
from thief_peer.peer.handshake import run_handshake
from thief_peer.peer.round_loop import play_round

_SENDER = "thief"

# Found by an actual live run against her real process, not by inspection:
# her own report_game() always calls this side's receive_final_reveal as
# part of *her* end-of-game sequence, even though this side's own
# finalize_match skips the (incompatible) audit exchange and returns
# immediately in cop_v1 mode. Her round loop's own pace turned out slower
# than this side's (a live run showed even 5s of blind sleep wasn't enough)
# -- cop_shutdown_grace waits for her actual call instead of guessing a
# fixed duration, this ceiling is only the safety net if she never calls at
# all (e.g. she crashed independently).
SHUTDOWN_GRACE_CEILING_SECONDS = 60.0

# The event fires the instant handle_receive_final_reveal's body runs, not
# after FastMCP has actually flushed the HTTP response back over the wire
# to her -- also found by a live run: exiting (tearing down the server)
# immediately after the event cut her connection mid-response, which her
# client reported as its own 30s DeadlineExceededError rather than a clean
# acknowledged reply. A short buffer lets the in-flight response land first.
RESPONSE_FLUSH_SECONDS = 2.0


def maybe_register_cop_tools(runtime) -> None:
    """Called once, right after `runtime.server_app` is built -- exposes
    her exact tool vocabulary on the same server alongside the native
    tools, so an inbound call from a real Cop client lands correctly even
    though this side initiated the connection natively. The adapter is
    stashed on `runtime` so `cop_shutdown_grace` can wait on its
    `final_reveal_received` event."""
    if runtime.opponent_protocol != "cop_v1":
        return
    adapter = CopContextAdapter(runtime, runtime.shared_config_path, runtime.sub_game_number)
    register_cop_tools(runtime.server_app, adapter)
    runtime._cop_adapter = adapter


def run_opponent_handshake(runtime) -> str:
    if runtime.opponent_protocol == "cop_v1":
        response = cop_step0_handshake(
            runtime.transport,
            runtime.config,
            runtime.group_name,
            runtime.sub_game_number,
            runtime.shared_config_path,
            runtime.repos,
        )
        return response["declaration"]["group_name"]
    their_step0 = run_handshake(
        runtime.config, runtime.transport, runtime.group_name, runtime.shared_config_path
    )
    return their_step0["payload"]["group_name"]


def cop_shutdown_grace(runtime) -> None:
    if runtime.opponent_protocol == "cop_v1":
        runtime._cop_adapter.final_reveal_received.wait(timeout=SHUTDOWN_GRACE_CEILING_SECONDS)
        time.sleep(RESPONSE_FLUSH_SECONDS)


def send_opponent_final_reveal(runtime, records: list[dict]) -> None:
    """Only meaningful for `cop_v1` -- native match-end uses its own
    `submit_audit`/`get_revealed_records` exchange instead
    (`peer/match_end.py`). `cop_send_final_reveal` was fully built (PRD 9)
    but never actually called in `cop_v1` mode until now; wiring it up lets
    her side's own `integrity/audit.py::run_mutual_audit` genuinely verify
    this peer's per-turn commits, now that `sealed_step_record` hashes her
    same 7-field envelope shape. This only closes *her* auditing *us* --
    there is no documented tool on her side for the reverse (pulling her
    own revealed records for this peer to audit her), so `match_end.py`'s
    own `opponent_audited_by_me` honestly stays unevaluated for `cop_v1`;
    closing that fully would need a new tool on her side, not this one."""
    if runtime.opponent_protocol != "cop_v1":
        return
    nonces, intents = build_cop_final_reveal_payload(records)
    cop_send_final_reveal(runtime.transport, nonces, intents)


def play_opponent_round(runtime, step: int) -> tuple[dict, dict, bool]:
    if runtime.opponent_protocol == "cop_v1":
        return play_round_cop(
            step,
            runtime.turn_handler,
            runtime.turn_fsm,
            runtime.scent,
            runtime.trash_talk,
            runtime.transport,
            runtime._last_opponent_scent,
        )
    return play_round(
        step,
        runtime.turn_handler,
        runtime.turn_fsm,
        runtime.scent,
        runtime.trash_talk,
        runtime.round_exchange,
        runtime.transport,
        _SENDER,
        runtime.round_deadline_sec,
        runtime._last_opponent_scent,
    )
