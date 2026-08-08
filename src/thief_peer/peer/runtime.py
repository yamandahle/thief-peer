"""PeerRuntime (PRD_8 §2.5, §3; PLAN.md C4): the single orchestrator wiring
negotiate -> the per-round commit/reveal loop -> end-of-match audit ->
report, entirely by reusing Stages 1-7's already-built pieces (TurnHandler,
handshake, sealing, negotiation, report_writer) -- no new game logic here,
only wiring. Game-component construction, the round loop, the
`infra/mcp_server.py` context handlers, and the end-of-match sequence live
in `peer/runtime_setup.py`, `peer/round_loop.py`, `peer/runtime_context.py`,
and `peer/match_end.py` respectively, kept out of this class to stay under
this codebase's file-length convention. `verdict` is left at `Decision`'s
"truth" default rather than wired to `strategy.trash_talk.choose_verdict` --
that function needs an expected-distance figure `ThiefBrain` only computes
as a private method; reaching into it (or duplicating its formula here) was
judged out of proportion to this stage's actual scope. Flagged, not hidden.
"""

from pathlib import Path

from thief_peer.domain.rules import has_survived, is_captured_by_stuck
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import build_server, run_server_in_background
from thief_peer.peer.handshake import run_handshake
from thief_peer.peer.match_end import finalize_match
from thief_peer.peer.round_exchange import RoundExchange
from thief_peer.peer.round_loop import play_round
from thief_peer.peer.runtime_context import PeerContextMixin
from thief_peer.peer.runtime_setup import build_game_components
from thief_peer.peer.turn_fsm import TurnFsm

_SENDER = "thief"


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
        sub_game_number: int = 1,
        num_sub_games: int = 1,
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

        components = build_game_components(config)
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

        self.port = config.require("network.my_port")
        self.opponent_url = config.get("network.opponent_url")
        self.server_app = build_server(self.port, self)
        self.transport = McpTransport(self.opponent_url) if self.opponent_url else None

    # --- match lifecycle ---

    def run(self) -> dict:
        run_server_in_background(self.server_app, self.port)
        their_step0 = run_handshake(self.config, self.transport, self.group_name)
        opponent_group_name = their_step0["payload"]["group_name"]

        end_reason = "max_moves_reached"
        step = 0
        while step < self.max_moves:
            step += 1
            record, self._last_opponent_scent, technical_loss = play_round(
                step,
                self.turn_handler,
                self.turn_fsm,
                self.scent,
                self.trash_talk,
                self.round_exchange,
                self.transport,
                _SENDER,
                self.round_deadline_sec,
                self._last_opponent_scent,
            )
            self.records.append(record)
            if technical_loss:
                end_reason = "technical_loss"
                break
            if has_survived(self.state, self.survival_threshold):
                end_reason = "survived"
                break
            if is_captured_by_stuck(self.state, self.board) or self._captured_by_barrier:
                end_reason = "captured"
                break

        self._match_over = True
        return finalize_match(
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
        )

    def view(self):
        from thief_peer.gui.window import PeerView

        return PeerView(
            own_position=self.state.position,
            belief_matrix=self.turn_handler.belief.as_matrix(),
            turn_state=self.turn_fsm.state,
            step_count=self.state.step_count,
        )
