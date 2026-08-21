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

`runtime.transport` (infra/mcp_client.py::McpTransport) is used exactly
as `PeerRuntime.__init__` already builds it for every other protocol --
one persistent connection for the whole series, not a fresh one per
call -- and `runtime.trash_talk` is the same single, already-constructed
collaborator `PeerRuntime` builds once in `__init__` for the native/
cop_v1 loops (peer/runtime_setup.py::build_game_components), reused here
for the whole std_v1 series rather than rebuilt per sub-game, matching
peer/round_loop.py's own established lifetime for it.

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
import time
from pathlib import Path

from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.domain.scent import ScentField
from thief_peer.exceptions import DeadlineExceededError, TransportError
from thief_peer.infra import email_sender
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.interop.std_v1 import replay_log
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.identity import build_identity
from thief_peer.interop.std_v1.scent_model_lock import build_scent_model_lock
from thief_peer.interop.std_v1.series_runner import play_series
from thief_peer.interop.std_v1.server_registration import register_std_v1_tools
from thief_peer.interop.std_v1.terms import DEFAULT_TERMS_PATH, load_terms
from thief_peer.peer.turn_fsm import TurnFsm
from thief_peer.peer.turn_handler import TurnHandler
from thief_peer.report.artifacts import build_config, build_declaration, build_log
from thief_peer.report.report_writer import LeagueCounter, send_report_email
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
    # `games_played_including_this` (final_result) / `games_played_against_
    # opponent` (declaration) both need this *before* the series starts --
    # native computes the equivalent inside `report/report_writer.py::
    # write_and_send`, but std_v1 builds its whole final report in one shot
    # inside `play_series` rather than incrementally across separate
    # process invocations, so this side has to compute it up front and
    # thread it in. Same `LeagueCounter`/`results/league_counter.json`
    # native already uses -- one shared, protocol-agnostic counter file.
    league_counter = LeagueCounter(Path(runtime.results_dir) / "league_counter.json")
    # rule-38/9.2.1 (verified against the book's own text, printed p.70,
    # not guessed): the Game-Count Declaration is "how many games it has
    # played so far" -- unqualified, a league-wide running total, not a
    # per-opponent count. `total_games_played()` sums the same underlying
    # per-opponent storage `record_game()` still writes to below (rule 52's
    # own one-counted-game-per-opponent enforcement is unaffected -- this
    # is only a second view over that data for the declared number). Must
    # be read first, since record_game() below mutates the same persisted
    # counter for a counted run, and reading it after would silently
    # return the post-increment total instead of what the negotiate
    # greeting is actually supposed to declare.
    counted_games_played = league_counter.total_games_played()
    # Rule 38/52 integrity fix: the counted-game slot must NOT be consumed
    # here, before the series has even started -- a real risk yanell11's
    # own team named explicitly ("if yours is missing, late, or
    # unconfirmed, both teams score zero -- we've each burned our one
    # counted game"), and one this repo used to hit literally: an attempt
    # run with is_counted=True that later ends unconfirmed (peer envelope
    # never arrives) would already have spent the slot for nothing.
    # `games_played` here is only the *declared* number for this attempt's
    # own identity/negotiate offer and report -- the real, persisted
    # increment happens in `peer/runtime.py::run()`, only once this
    # series' own `mutual_agreement.confirmed` is actually known. The
    # `LeagueCounter`/opponent id are stashed on `runtime` for that later
    # call to use.
    games_played = counted_games_played + 1 if runtime.is_counted else counted_games_played
    runtime._league_counter = league_counter
    runtime._their_group_id = their_group_id
    # `network.public_url` is optional -- the localhost address is real and
    # correct for actually running the server, but useless to a peer
    # reading the filed report to see how to reach us (reconciled live
    # against yanell11). No code here can discover a tunnel's own assigned
    # public hostname on its own (ngrok picks it dynamically), so this is
    # a config value the operator fills in for the current match rather
    # than something auto-detected.
    reported_server_url = runtime.config.get("network.public_url") or f"http://127.0.0.1:{runtime.port}/mcp"
    identity = build_identity(
        group_id=my_group_id,
        group_name=runtime.group_name,
        members=runtime.config.get("std_v1.members", []),
        repos=runtime.repos,
        mcp_servers={
            "thief": reported_server_url,
            "cop": reported_server_url,
        },
        llm_model=runtime.config.get("llm.model", "template"),
        scent_model_lock=build_scent_model_lock(terms),
        counted_games_played=counted_games_played,
    )

    # Each factory below also assigns its object onto `runtime` itself, on
    # top of returning it to series_runner.py -- `board`/`state` are then
    # mutated in place turn-by-turn by round_loop.py/police_round_loop.py,
    # so `PeerRuntime.view()` (peer/runtime.py, already polled live by
    # gui/live_session.py::LiveSession for the native/cop_v1 path) starts
    # reflecting real std_v1 play instead of the frozen state left over
    # from `__init__`. This is the only wiring the live GUI needs -- no
    # changes to series_runner.py/round_loop.py/police_round_loop.py or the
    # gui package itself, since `view()` already reads generically off
    # `runtime.state`/`runtime.turn_handler`.
    def board_factory() -> Board:
        board = Board(size=terms["board_size"], barriers=set())
        runtime.board = board
        return board

    def state_factory(role: str) -> OwnGameState:
        position = terms["thief_start"] if role == "thief" else terms["cop_start"]
        state = OwnGameState(position=tuple(position))
        runtime.state = state
        return state

    def turn_handler_factory(board, state) -> TurnHandler:
        turn_handler = TurnHandler(board, state, resolve_brain(runtime.config))
        runtime.turn_handler = turn_handler
        return turn_handler

    def scent_factory() -> ScentField:
        return ScentField(
            board_size=terms["board_size"],
            center_intensity=terms["emit_intensity"],
            decay_rate=terms["decay_per_step"],
        )

    def turn_fsm_factory() -> TurnFsm:
        # A *fresh* TurnFsm every sub-game, not a shared one -- see
        # series_runner.py::play_series's own docstring for why reusing one
        # instance across sub-game boundaries would raise on sub-game 2's
        # first transition. Assigned onto `runtime.turn_fsm` too so
        # `view()`'s `turn_state` (feeding gui/turn_banner.py) reflects
        # whichever sub-game is currently live.
        turn_fsm = TurnFsm()
        runtime.turn_fsm = turn_fsm
        return turn_fsm

    # rule 1/2: real Police decisions must come from a genuinely separate
    # `yamanagh-cop` process, not this repo's own built-in `police_brain.py`
    # stand-in. `network.cop_relay_url`, if configured, points at that
    # process's loopback relay port (see interop/std_v1/police_relay_loop.py
    # and yamanagh-cop's own std_v1/relay_server.py); left unset, every even
    # sub-game keeps using the old built-in stand-in unchanged -- an opt-in
    # switch so this can be verified once, locally, before relying on it in
    # a real match, and reverted instantly by removing the one config key.
    cop_relay_url = runtime.config.get("network.cop_relay_url")
    police_relay_transport = McpTransport(cop_relay_url) if cop_relay_url else None
    # Rule 49/[REPORT] accuracy: the relayed Police sub-games are really
    # played by yamanagh-cop's own commit, not this process's -- fetched
    # once up front (the relay's own commit doesn't change mid-series) and
    # threaded through so the filed report attributes each sub-game to the
    # repo that actually played it, not uniformly to this one. Best-effort:
    # a relay that's briefly unreachable for this one call must not abort
    # the whole series before it even starts -- report.py already falls
    # back to this process's own commit when `cop_github_commit` is None.
    cop_github_commit = None
    if police_relay_transport is not None:
        try:
            cop_github_commit = police_relay_transport.call("relay_identity", {})["github_commit"]
        except (DeadlineExceededError, TransportError) as exc:
            print(f"[relay] could not fetch yamanagh-cop's own commit for reporting: {exc}", flush=True)
    try:
        result = play_series(
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
            runtime.trash_talk,
            turn_deadline_sec=runtime.round_deadline_sec,
            turn_fsm_factory=turn_fsm_factory,
            games_played_including_this=games_played,
            counted_games_played=counted_games_played,
            police_relay_transport=police_relay_transport,
            cop_github_commit=cop_github_commit,
            is_counted=runtime.is_counted,
        )
    finally:
        if police_relay_transport is not None:
            police_relay_transport.close()
    write_std_v1_log(result, runtime.results_dir)
    write_std_v1_declaration(result, terms, runtime.results_dir, games_played)
    write_std_v1_config(result, terms, runtime.results_dir)
    return result


def write_std_v1_log(result: dict, results_dir: str | Path) -> Path:
    """Persists this side's own revealed records for the whole series as
    `results/log_<game_uid>.json` -- the replay-log counterpart to
    `write_std_v1_result`'s `result_<game_id>.json`, using the exact same
    `report/artifacts.py::build_log` builder native/cop_v1 already use
    (tagged `protocol="std_v1"` so `gui/replay_view.py` verifies it with
    the right commit-reveal scheme). One file for the whole series, not
    per sub-game -- std_v1's `game_uid` is series-scoped, unlike native's
    own per-sub-game `game_uid`."""
    records = result["records"]
    audit = replay_log.audit_records(records)
    log = build_log(records, audit, protocol="std_v1")
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"log_{result['game_uid']}.json"
    out_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return out_path


def write_std_v1_declaration(
    result: dict, terms: dict, results_dir: str | Path, games_played: int
) -> Path:
    """The series' `declaration_<game_id>.json` -- native's own `report/
    artifacts.py::build_declaration`, called directly rather than through
    `report/report_writer.py::write_and_send` (that function's own
    `merge_sub_game_into_series` assumes native's one-sub-game-per-process
    model; std_v1 already has its whole series' data in `result` by the
    time this runs). `games_played_against_opponent`: same precedent as
    native's own report_writer.py -- a separate key from `final_result`'s
    `games_played_including_this`, same underlying counter value."""
    declaration = build_declaration(
        game_id=result["game_id"],
        game_uid=result["game_uid"],
        num_sub_games=terms["num_games"],
        groups=result["report"]["groups"],
    )
    declaration["games_played_against_opponent"] = games_played
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"declaration_{result['game_id']}.json"
    out_path.write_text(json.dumps(declaration, indent=2), encoding="utf-8")
    return out_path


def write_std_v1_config(result: dict, terms: dict, results_dir: str | Path) -> Path:
    """The series' `config_<game_uid>.json` -- one file for the whole
    series (std_v1's `terms` don't change per sub-game), unlike native's
    own per-sub-game config file."""
    config = build_config(terms, config_name=f"config_{result['game_uid']}")
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"config_{result['game_uid']}.json"
    out_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return out_path


LEAGUE_RESULT_EMAIL = "rmisegal+uoh26finalgame@gmail.com"

# Real bug found live against moamteam (their own diagnosis, confirmed
# against this repo's own code): this side's MCP server tears down the
# instant PeerRuntime.run() returns, with no equivalent to
# interop/cop_opponent.py's own cop_shutdown_grace -- an in-flight final
# call from the peer (their own audit/consensus retry, or just their
# session's own close) can land against an already-dead server. That
# exact failure hit US once already this session, from the other side
# (moamteam's own process tore down mid-exchange) -- this closes the
# same gap on our own side before it does the same thing to a future
# opponent who finishes after we do.
STD_V1_SHUTDOWN_GRACE_SECONDS = 20.0


def std_v1_shutdown_grace() -> None:
    """Unlike cop_v1's own event-based wait (a specific "she called back"
    signal to wait on), std_v1 has no equivalent confirmation to wait for
    -- this is a simple fixed hold, matching moamteam's own fix for the
    identical problem on their side."""
    time.sleep(STD_V1_SHUTDOWN_GRACE_SECONDS)


def send_std_v1_report_email(result: dict, runtime, *, is_counted: bool) -> bool:
    """Rule 32: both teams' agents must each email their own copy of the
    final result. Reuses `report/report_writer.py::send_report_email`
    verbatim -- the exact same gatekeeper-wrapped Gmail-send call and
    best-effort failure handling native's own `write_and_send` uses, just
    invoked directly here since std_v1 doesn't go through that function's
    own native-shaped `write_and_send` pipeline. Called from `PeerRuntime.
    run()` after `write_std_v1_result` has already put `result["report"]`
    on disk, so a failed send never loses the result itself (rules 33/34).

    `is_counted` here is the caller's *effective* decision (attempted-as-
    counted AND `mutual_agreement.confirmed`), not simply `runtime.
    is_counted` -- see `PeerRuntime.run()`'s own confirmation gate. An
    attempt run as counted that ends unconfirmed must not reach the
    lecturer as though it were a real result (the whole point of this
    fix): both teams score zero for the series if the filing turns out to
    be missing/unconfirmed on either side, which is exactly the outcome
    this gate exists to prevent for an obviously-incomplete run.

    Rules 9.3/35: a genuinely *counted* series' result MUST reach the
    fixed league address automatically -- never left to whatever `[email]
    recipient` happens to be configured, which is one manual edit away
    from being forgotten right before the one run that actually counts.
    `[email] recipient` is CC'd on every send regardless (so the opponent
    can diff against their own filing) -- an uncounted/warm-up run already
    used that same address as its sole recipient, so `build_recipients`'
    own `is_counted` gate (email_sender.py) is what adds the league
    address on top for a counted run instead of replacing the opponent
    address outright."""
    recipient = email_sender.build_recipients(
        LEAGUE_RESULT_EMAIL, runtime.recipient, is_counted=is_counted
    )
    return send_report_email(runtime.gatekeeper, runtime.email_service, recipient, result["report"])


def write_std_v1_result(result: dict, results_dir: str | Path) -> Path:
    """Section 12/18 [MUST]: filename is exactly `result_<game_id>.json`
    (no protocol prefix -- this is the one submitted artifact, not an
    internal debug dump), containing `result["report"]`'s own Section-12
    shape (`interop/std_v1/report.py::build_result_report`), not the raw
    `play_series` return value (which also carries the canonical
    consensus object and other diagnostic-only fields never part of the
    submitted report)."""
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"result_{result['game_id']}.json"
    out_path.write_text(json.dumps(result["report"], indent=2), encoding="utf-8")
    return out_path
