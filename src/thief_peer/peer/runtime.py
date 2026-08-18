"""PeerRuntime (PRD_8 §2.5, §3; PLAN.md C4): the single orchestrator wiring
negotiate -> the per-round commit/reveal loop -> end-of-match audit ->
report, entirely by reusing Stages 1-7's already-built pieces (TurnHandler,
handshake, sealing, negotiation, report_writer) -- no new game logic here,
only wiring. Game-component construction, the round loop, the
`infra/mcp_server.py` context handlers, the end-of-match sequence, and the
rule-7 watchdog's heartbeat producer live in `peer/runtime_setup.py`,
`peer/round_loop.py`, `peer/runtime_context.py`, `peer/match_end.py`, and
`peer/heartbeat_monitor.py` respectively, kept out of this class to stay
under this codebase's file-length convention. `verdict` is left at `Decision`'s
"truth" default rather than wired to `strategy.trash_talk.choose_verdict` --
that function needs an expected-distance figure `ThiefBrain` only computes
as a private method; reaching into it (or duplicating its formula here) was
judged out of proportion to this stage's actual scope. Flagged, not hidden.
"""

import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path

from thief_peer.domain.rules import has_survived, is_captured_by_stuck
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import build_server, run_server_in_background
from thief_peer.interop.cop_opponent import (
    cop_shutdown_grace,
    maybe_register_cop_tools,
    play_opponent_round,
    run_opponent_handshake,
    send_opponent_final_reveal,
)
from thief_peer.interop.cop_wire import current_git_commit_hash
from thief_peer.interop.std_v1_opponent import (
    maybe_register_std_v1_tools,
    run_std_v1_series,
    write_std_v1_result,
)
from thief_peer.peer.heartbeat_monitor import HeartbeatMonitor
from thief_peer.peer.match_end import finalize_match
from thief_peer.peer.round_exchange import RoundExchange
from thief_peer.peer.runtime_context import PeerContextMixin
from thief_peer.peer.runtime_setup import build_game_components
from thief_peer.peer.turn_fsm import TurnFsm


class PeerRuntime(PeerContextMixin):
    def __init__(
        self,
        config,
        group_name: str,
        gatekeeper,
        email_service,
        recipient: str,
        results_dir: str | Path = "results",
        round_deadline_sec: float = 30.0,
        strategy_deadline_sec: float = 30.0,
        watchdog_timeout_sec: float = 180.0,
        sub_game_number: int = 1,
        num_sub_games: int = 1,
        is_counted: bool = True,
        shared_config_path: str | None = None,
    ):
        self.config = config
        self.group_name = group_name
        self.gatekeeper = gatekeeper
        self.email_service = email_service
        self.recipient = recipient
        self.results_dir = results_dir
        self.round_deadline_sec = round_deadline_sec
        self.strategy_deadline_sec = strategy_deadline_sec
        self.sub_game_number = sub_game_number
        self.num_sub_games = num_sub_games
        self.is_counted = is_counted
        self.repos = config.get("repos", {})
        # "native" (default) speaks this repo's own vocabulary; "cop_v1"
        # switches to the Cop-repo interop adapter (interop/cop_opponent.py).
        self.opponent_protocol = config.get("network.opponent_protocol", "native")
        self.shared_config_path = shared_config_path
        self.heartbeat = HeartbeatMonitor(timeout_sec=watchdog_timeout_sec)

        components = build_game_components(config, self.gatekeeper)
        self.board = components.board
        self.state = components.state
        self.turn_handler = components.turn_handler
        self.scent = components.scent
        self.trash_talk = components.trash_talk
        self.survival_threshold = components.survival_threshold
        self.max_moves = components.max_moves

        self.turn_fsm = TurnFsm()
        self.round_exchange = RoundExchange()
        self.records: list[dict] = []
        self._last_opponent_scent: dict[str, float] = {}
        self._match_over = False
        self._captured_by_barrier = False
        self._captured_by_landing = False
        # Set alongside _captured_by_landing (interop/cop_server_tools.py::
        # handle_receive_capture_claim, on the MCP server's own thread) so a
        # blocking wait_for_reveal() on the main loop's thread can wake up
        # immediately instead of running out its full round_deadline_sec --
        # found via a real live match: her cop peer treats a confirmed
        # capture as terminal and never sends the next round's reveal, but
        # this side's own _captured_by_landing check only ever ran at a
        # round boundary, so a confirmation landing mid-wait for the *next*
        # round left the loop blocked for the full deadline before timing
        # out as a false technical_loss instead of ending cleanly as
        # "captured" at the round that actually caught it.
        self._round_wakeup = threading.Event()

        self.port = config.require("network.my_port")
        self.opponent_url = config.get("network.opponent_url")
        self.server_app = build_server(self.port, self)
        maybe_register_cop_tools(self)
        maybe_register_std_v1_tools(self)
        # `round_deadline_sec` is this side's own copy of the shared,
        # negotiated `network_and_league.response_timeout_sec` (docs/
        # todoFIXMCP.md's config-audit) -- reused here rather than
        # McpTransport's own separate hardcoded default, so a single
        # config change actually bounds every MCP call, not just the
        # round-level wait_for_reveal.
        self.transport = (
            McpTransport(self.opponent_url, response_timeout_sec=self.round_deadline_sec)
            if self.opponent_url
            else None
        )

    # --- match lifecycle ---

    def run(self) -> dict:
        started_at = datetime.now(UTC).isoformat()
        run_server_in_background(self.server_app, self.port)
        if self.opponent_protocol == "std_v1":
            # std_v1's own match lifecycle (per-sub-game negotiation, a
            # shared step counter, a final series-consensus exchange) does
            # not fit the native/cop_v1 single-match loop below at all --
            # interop/std_v1_opponent.py::run_std_v1_series runs the
            # entire num_games-sub-game series itself and returns its own
            # summary dict.
            result = run_std_v1_series(self)
            write_std_v1_result(result, self.results_dir)
            if self.transport is not None:
                self.transport.close()
            return result
        self.heartbeat.start()
        opponent = run_opponent_handshake(self)
        opponent_group_name = opponent["group_name"]

        end_reason = "max_moves_reached"
        technical_loss_reason: str | None = None
        technical_loss_traceback: str | None = None
        step = 0
        while step < self.max_moves:
            if self._captured_by_landing:
                # A confirmed capture landed between rounds (its own
                # wakeup already fired mid-wait for the round it
                # interrupted, if any) -- never start a new round we
                # already know can't complete.
                end_reason = "captured"
                break
            step += 1
            # Wall-clock anchor for this round, persisted alongside the
            # reason below -- docs/todoFIXMCP.md's investigations kept
            # needing to cross-reference a failure against an *external*
            # log (the peer's own report, the ngrok inspector's own
            # request timestamps) with nothing better than "sometime
            # before this match's ended_at" to go on. An absolute
            # timestamp on the specific round that failed makes that a
            # direct lookup instead of a wide, manual time-window search.
            round_started_at = datetime.now(UTC).isoformat()
            try:
                record, self._last_opponent_scent, technical_loss, round_reason = (
                    play_opponent_round(self, step)
                )
            except Exception as exc:
                # Ch.8.4: the system must never silently crash. An illegal
                # FSM transition (a misbehaving/out-of-protocol opponent)
                # or a genuinely unexpected bug here must still produce a
                # real, scored match result -- not an unhandled crash with
                # no final log/report, which would void the game under
                # rule 35 far worse than a clean technical loss would.
                # Previously this reason only ever went to stdout and was
                # lost the moment the terminal scrolled past it -- a real
                # post-mortem (docs/todoFIXMCP.md) needed the exact
                # exception type/message and had no artifact to read it
                # from. Now also persisted onto the report itself.
                technical_loss_reason = (
                    f"round {step} (started {round_started_at}): {type(exc).__name__}: {exc}"
                )
                # This path is specifically the *unexpected*-bug catch-all
                # (every well-understood network failure is caught inside
                # play_opponent_round itself, with its own descriptive
                # round_reason instead) -- worth the full traceback, not
                # just the exception's own string, since there's no
                # existing "which check failed" context to fall back on.
                technical_loss_traceback = traceback.format_exc()
                print(f"[technical-loss] {technical_loss_reason}")
                end_reason = "technical_loss"
                break
            self.records.append(record)
            self.heartbeat.beat()
            if technical_loss:
                technical_loss_reason = f"round {step} (started {round_started_at}): {round_reason}"
                end_reason = "technical_loss"
                break
            if has_survived(self.state, self.survival_threshold):
                end_reason = "survived"
                break
            if (
                is_captured_by_stuck(self.state, self.board)
                or self._captured_by_barrier
                or self._captured_by_landing
            ):
                end_reason = "captured"
                break

        self.heartbeat.stop()
        self._match_over = True
        self_audit = None
        opponent_audit = None
        if self.opponent_protocol == "cop_v1":
            # Ch.5.3.2 order: reveal our nonces (she audits us and returns
            # the summary), wait for hers, audit her locally, then report.
            self_audit = send_opponent_final_reveal(self, self.records)
            cop_shutdown_grace(self)
            opponent_audit = self._cop_adapter.opponent_audit
        else:
            send_opponent_final_reveal(self, self.records)
        result = finalize_match(
            self.group_name,
            opponent_group_name,
            end_reason,
            self.records,
            self.config,
            self.transport,
            self.gatekeeper,
            self.email_service,
            self.recipient,
            self.results_dir,
            self.sub_game_number,
            self.num_sub_games,
            self.repos,
            self.is_counted,
            self.opponent_protocol,
            precomputed_self_audit=self_audit,
            precomputed_opponent_audit=opponent_audit,
            started_at=started_at,
            our_github_commit=current_git_commit_hash(),
            opponent_github_commit=opponent.get("github_commit"),
            technical_loss_reason=technical_loss_reason,
            technical_loss_traceback=technical_loss_traceback,
        )
        if self.opponent_protocol != "cop_v1":
            cop_shutdown_grace(self)
        if self.transport is not None:
            self.transport.close()
        return result

    def view(self):
        from thief_peer.gui.window import PeerView

        return PeerView(
            own_position=self.state.position,
            belief_matrix=self.turn_handler.belief.as_matrix(),
            turn_state=self.turn_fsm.state,
            step_count=self.state.step_count,
        )
