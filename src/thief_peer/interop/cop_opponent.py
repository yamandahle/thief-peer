"""Opponent-protocol dispatch for `PeerRuntime`: routes handshake/round-loop
calls to either the native Thief vocabulary or the Cop interop adapter,
based on `network.opponent_protocol` in config ("native", the default, or
"cop_v1"). Free functions taking `runtime` explicitly, matching this
codebase's existing preference (`peer/handshake.py`, `peer/round_loop.py`)
for injectable collaborators over deep object coupling -- kept out of
`peer/runtime.py` itself, which is already at this project's 150-line cap.
"""

from thief_peer.interop.cop_handshake import cop_step0_handshake
from thief_peer.interop.cop_round_loop import play_round_cop
from thief_peer.interop.cop_server_tools import CopContextAdapter, register_cop_tools
from thief_peer.peer.handshake import run_handshake
from thief_peer.peer.round_loop import play_round

_SENDER = "thief"


def maybe_register_cop_tools(runtime) -> None:
    """Called once, right after `runtime.server_app` is built -- exposes
    her exact tool vocabulary on the same server alongside the native
    tools, so an inbound call from a real Cop client lands correctly even
    though this side initiated the connection natively."""
    if runtime.opponent_protocol != "cop_v1":
        return
    adapter = CopContextAdapter(runtime, runtime.shared_config_path, runtime.sub_game_number)
    register_cop_tools(runtime.server_app, adapter)


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
    their_step0 = run_handshake(runtime.config, runtime.transport, runtime.group_name)
    return their_step0["payload"]["group_name"]


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
