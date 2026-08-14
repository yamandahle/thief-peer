"""PeerRuntime (PRD_8 §2.5, §3; PLAN.md C4): the single orchestrator wiring
negotiate -> the per-round commit/reveal loop -> end-of-match audit ->
report, entirely by reusing Stages 1-7's already-built pieces (TurnHandler,
handshake, sealing, negotiation, report_writer) -- no new game logic here,
only wiring. Game-component construction, the round loop, the
`infra/mcp_server.py` context handlers, the end-of-match sequence, and the
rule-7 watchdog's heartbeat producer live in `peer/runtime_setup.py`,
`peer/round_loop.py`, `peer/runtime_context.py`, `peer/match_end.py`, and
`peer/heartbeat_monitor.py` respectively, kept out of this class to stay
under this codebase's file-length convention. `verdict` (book ch.6.5/1.4)
is decided by the brain itself now (`BrainBase._choose_verdict`,
`ThiefBrain`'s own override reusing its private `_expected_distance`) --
`decide()` sets it on every `Decision` it returns, so this class never
needs to reach into the brain's internals.
"""

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
from thief_peer.peer.heartbeat_monitor import HeartbeatMonitor
from thief_peer.peer.match_end import finalize_match
from thief_peer.peer.round_exchange import RoundExchange
from thief_peer.peer.round_reporter import print_match_summary, print_round_summary
from thief_peer.peer.runtime_context import PeerContextMixin
from thief_peer.peer.runtime_setup import build_game_components
from thief_peer.peer.sealing import current_git_commit_hash
from thief_peer.peer.turn_fsm import TurnFsm
from thief_peer.shared import sysinfo


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
        watchdog_timeout_sec: float = 180.0,
        sub_game_number: int = 1,
        num_sub_games: int = 1,
        is_counted: bool = True,
        shared_config_path: str | None = None,
        team_code: str | None = None,
    ):
        self.config = config
        self.group_name = group_name
        self.gatekeeper = gatekeeper
        self.email_service = email_service
        self.recipient = recipient
        self.results_dir = results_dir
        self.round_deadline_sec = round_deadline_sec
        self.sub_game_number = sub_game_number
        self.num_sub_games = num_sub_games
        self.is_counted = is_counted
        # Rule 45 [MUST]: a separate, optional 8-char Moodle/report code --
        # already validated at the CLI (shared/team_code.py) before this
        # constructor ever runs, if the caller supplied one at all.
        self.team_code = team_code
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
        self._last_opponent_hint: str = ""
        self._match_over = False
        self._captured_by_barrier = False
        self._captured_by_landing = False
        self.opponent_repos: dict = {}
        self.opponent_llm_model: str | None = None
        self._tokens_used = 0

        self.port = config.require("network.my_port")
        self.opponent_url = config.get("network.opponent_url")
        self.server_app = build_server(self.port, self)
        maybe_register_cop_tools(self)
        self.transport = McpTransport(self.opponent_url) if self.opponent_url else None

    # --- match lifecycle ---

    def run(self) -> dict:
        run_server_in_background(self.server_app, self.port)
        self.heartbeat.start()
        started_at = datetime.now(UTC).isoformat()
        opponent_group_name = run_opponent_handshake(self)

        end_reason = "max_moves_reached"
        step = 0
        while step < self.max_moves:
            step += 1
            record, self._last_opponent_scent, self._last_opponent_hint, technical_loss = (
                play_opponent_round(self, step)
            )
            self.records.append(record)
            print_round_summary(
                step,
                self.max_moves,
                self.group_name,
                opponent_group_name,
                record,
                self._last_opponent_hint,
                len(self.state.known_barriers),
                self.state.position,
                self.survival_threshold,
                hint_agreement=self.turn_handler.hint_agreement_log[-1],
            )
            self.heartbeat.beat()
            if technical_loss:
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
        ended_at = datetime.now(UTC).isoformat()
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
        my_url = f"http://127.0.0.1:{self.port}/mcp"
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
            opponent_repos=self.opponent_repos,
            tokens_own=self._tokens_used,
            game_started_at=started_at,
            game_ended_at=ended_at,
            own_llm_model=self.config.get("llm.model", "template"),
            opponent_llm_model=self.opponent_llm_model,
            own_mcp_url=my_url,
            opponent_mcp_url=self.opponent_url,
            own_spec=sysinfo.collect_spec(),
            github_commit_own=current_git_commit_hash(),
            own_team_code=self.team_code,
            shared_config_path=self.shared_config_path,
        )
        if self.opponent_protocol != "cop_v1":
            cop_shutdown_grace(self)
        print_match_summary(result, self.group_name, self.turn_handler.hint_agreement_log)
        return result

    def view(self):
        from thief_peer.domain.scent import snapshot_to_matrix
        from thief_peer.gui.window import PeerView

        return PeerView(
            own_position=self.state.position,
            belief_matrix=self.turn_handler.belief.as_matrix(),
            turn_state=self.turn_fsm.state,
            step_count=self.state.step_count,
            scent_matrix=snapshot_to_matrix(self._last_opponent_scent, self.board.size),
            hint_text=self._last_opponent_hint,
        )
