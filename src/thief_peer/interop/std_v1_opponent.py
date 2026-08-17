"""Wiring `PeerRuntime` up to the std_v1 protocol (interop/std_v1/*):
selected by `network.opponent_protocol = "std_v1"` in config, same
one-value-in-a-TOML-file switch as `cop_opponent.py`'s own "cop_v1".

std_v1's match lifecycle (per-sub-game negotiation, its own shared step
counter, a final series-consensus exchange) does not fit the native/cop_v1
single-match round loop `PeerRuntime.run()` otherwise drives -- so this
mode is a genuine short-circuit: `run_std_v1_series` runs the *entire*
`num_games`-sub-game series itself via `interop/std_v1/series_runner.py`
and returns its own summary dict, never entering the native step-by-step
loop at all. `maybe_register_std_v1_tools` mirrors `cop_opponent.py::
maybe_register_cop_tools`'s "stash an exchange/adapter on runtime, right
after `server_app` is built" shape.

Spec Section 6/10 [MATCH] role alternation means this repo plays Police
on the even sub-games too (`interop/std_v1/police_round_loop.py`'s own
minimal brain) -- `state_factory` below is therefore role-aware, not
fixed to `thief_start`, and `mcp_servers` below declares both roles since
this one server now genuinely answers for both.

`ScentField(board_size=terms["board_size"], center_intensity=terms[
"emit_intensity"], decay_rate=terms["decay_per_step"])`: the mapping from
the spec's own term names to this class's constructor isn't spelled out
anywhere in the spec text itself, but `emit_intensity=0.9`/
`decay_per_step=0.1` are exactly this class's own existing defaults --
strong evidence the spec's authors modeled the same book formula this
repo already implements. `min_center_intensity` and `smell_grid_size`
have no local equivalent to map onto (this repo's `ScentField` has no
windowing/threshold concept) and are intentionally left unused here --
an interop risk to reconcile if a real match against another team's
Cop shows a mismatched smell_grid shape, not a bug in this mapping.
"""

from __future__ import annotations

import json
from pathlib import Path

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.scent import ScentField
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.identity import build_identity
from thief_peer.interop.std_v1.series_runner import play_series
from thief_peer.interop.std_v1.server_registration import register_std_v1_tools
from thief_peer.interop.std_v1.terms import DEFAULT_TERMS_PATH, load_terms
from thief_peer.peer.turn_handler import TurnHandler
from thief_peer.strategy.brain_base import resolve_brain


def maybe_register_std_v1_tools(runtime) -> None:
    if runtime.opponent_protocol != "std_v1":
        return
    runtime._std_v1_exchange = StdExchange()
    register_std_v1_tools(runtime.server_app, runtime._std_v1_exchange)


def run_std_v1_series(runtime) -> dict:
    """The whole std_v1 match, start to finish. Called instead of the
    native per-round loop when `runtime.opponent_protocol == "std_v1"` --
    see `PeerRuntime.run()`."""
    terms = load_terms(runtime.config.get("std_v1.terms_path", DEFAULT_TERMS_PATH))
    my_group_id = runtime.config.get("std_v1.group_id", runtime.group_name)
    # [REQUIRED] rule-6 game_uid derivation needs both group ids known
    # before negotiation starts -- unlike the native handshake, std_v1's
    # own step-0 offer already commits to a game_uid, so the peer's group
    # id can't be *learned* from that same handshake; it must be
    # configured up front (see game_std_v1_remote.toml.example).
    their_group_id = runtime.config.require("network.opponent_group_id")
    identity = build_identity(
        group_id=my_group_id,
        group_name=runtime.group_name,
        members=runtime.config.get("std_v1.members", []),
        repos=runtime.repos,
        mcp_servers={
            "thief": f"http://127.0.0.1:{runtime.port}/mcp",
            "cop": f"http://127.0.0.1:{runtime.port}/mcp",
        },
        llm_model=runtime.config.get("llm.model", "template"),
    )

    def board_factory() -> Board:
        return Board(size=terms["board_size"], barriers=set())

    def state_factory(role: str) -> OwnGameState:
        position = terms["thief_start"] if role == "thief" else terms["cop_start"]
        return OwnGameState(position=tuple(position))

    def turn_handler_factory(board, state) -> TurnHandler:
        return TurnHandler(board, state, resolve_brain(runtime.config))

    def scent_factory() -> ScentField:
        return ScentField(
            board_size=terms["board_size"],
            center_intensity=terms["emit_intensity"],
            decay_rate=terms["decay_per_step"],
        )

    return play_series(
        runtime.transport,
        runtime._std_v1_exchange,
        terms,
        my_group_id,
        their_group_id,
        identity,
        board_factory,
        state_factory,
        turn_handler_factory,
        scent_factory,
        turn_deadline_sec=runtime.round_deadline_sec,
    )


def write_std_v1_result(result: dict, results_dir: str | Path) -> Path:
    """Consensus_object (Section 11) is already the authoritative,
    both-sides-agreed record of the series -- unlike the native/cop_v1
    path, there's no separate report_writer schema to reuse here, only a
    plain dump of `play_series`'s own return value next to it."""
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"result_std_v1_{result['game_id']}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out_path
