"""CopContextAdapter: FastMCP handlers for the Cop repo's tool names.

Records her commit/reveal stream into `CopPeerTrace` and, on Final Reveal
(Ch.5.3.2), runs rules 19/36 peer audit — returning the summary so mutual
audit is visible on the wire, not only in her local report.
"""

import threading

from thief_peer.interop.cop_handshake import build_own_declaration, verify_their_declaration
from thief_peer.interop.cop_peer_audit import CopPeerTrace, audit_cop_peer_trace
from thief_peer.interop.cop_turn_sender import cop_send_capture_response
from thief_peer.interop.cop_wire import serialize_scent_for_cop, sign_cop_declaration

_NOT_EVALUATED = {
    "passed": False,
    "verified_steps": 0,
    "failed_steps": [],
    "failed_capture_claims": [],
    "evaluated": False,
}


def _log_deadline_metadata(tool_name: str, sent_at: float | None, deadline_at: float | None) -> None:
    """PRD_15's Deadline Tracker (Ch.8.4): a peer's own declared request
    timing, logged here for observability only. Rule 9 -- a peer-declared
    deadline is never trusted to affect the receiver's own behavior -- so
    this never feeds into our own FSM/round-deadline logic, only stdout."""
    if sent_at is not None or deadline_at is not None:
        print(f"[deadline-tracker] {tool_name}: peer sent_at={sent_at} deadline_at={deadline_at}")


class CopContextAdapter:
    def __init__(self, context, shared_config_path: str, sub_game_number: int = 1):
        self._context = context
        self._shared_config_path = shared_config_path
        self._sub_game_number = sub_game_number
        self._commit_step = 1
        self._reveal_step = 1
        self._last_commit_hash: str | None = None
        self._reveal_done_for_current_step = False
        self.final_reveal_received = threading.Event()
        self.peer_trace = CopPeerTrace()
        self.opponent_audit: dict = dict(_NOT_EVALUATED)

    def handle_receive_commit(
        self, h_commit: str, sent_at: float | None = None, deadline_at: float | None = None
    ) -> dict:
        _log_deadline_metadata("receive_commit", sent_at, deadline_at)
        if h_commit == self._last_commit_hash and not self._reveal_done_for_current_step:
            # docs/todoFIXMCP.md #2: a retried duplicate of the commit
            # we're still awaiting the matching reveal for. h_commit is
            # SHA-256(state, move, intent, nonce) with a fresh random
            # nonce every round (domain/crypto.py::CommitReveal.seal), so
            # an exact repeat this close together is a retry-echo, not a
            # legitimate new round -- re-ack without double-advancing
            # _commit_step, or the round numbering desyncs for the rest
            # of the match.
            return {"acknowledged": True}
        self._context.handle_commit_move({"step": self._commit_step, "h_commit": h_commit})
        self.peer_trace.record_commit(h_commit)
        self._commit_step += 1
        self._last_commit_hash = h_commit
        self._reveal_done_for_current_step = False
        return {"acknowledged": True}

    def handle_receive_reveal(
        self,
        move: dict,
        hint_text: str,
        sent_at: float | None = None,
        deadline_at: float | None = None,
    ) -> dict:
        _log_deadline_metadata("receive_reveal", sent_at, deadline_at)
        if self._reveal_done_for_current_step:
            # Same reasoning as the commit guard above, but move/hint_text
            # content can legitimately repeat between different rounds
            # (e.g. "STAY" with the same generated hint), so content
            # can't be compared the way h_commit's hash can -- step-
            # boundary tracking instead: a reveal already recorded for
            # the step whose commit is still the most recent one is a
            # retry-echo, not a new round's reveal.
            return {"accepted": True, "word_count": len(hint_text.split())}
        direction = move.get("direction", "STAY") if move.get("type") == "move" else "STAY"
        self._context.handle_reveal_move(
            {
                "step": self._reveal_step,
                "sender": "cop",
                "hint": hint_text,
                "scent_grid": {},
                "move": direction,
                "intent": "truth",
            }
        )
        self.peer_trace.record_reveal(move, hint_text)
        self._reveal_step += 1
        self._reveal_done_for_current_step = True
        return {"accepted": True, "word_count": len(hint_text.split())}

    def handle_share_scent_map(self) -> dict:
        return serialize_scent_for_cop(self._context.scent.snapshot())

    def handle_receive_barrier_declaration(self, col: int, row: int) -> dict:
        self._context.handle_receive_barrier_declaration({"row": row, "col": col})
        return {"acknowledged": True}

    def handle_receive_capture_claim(
        self, thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        my_row, my_col = self._context.state.position
        confirmed = (my_row, my_col) == (thief_row, thief_col)
        if confirmed:
            # Unlike a barrier capture (handled by the shared
            # PeerContextMixin.handle_receive_barrier_declaration, which
            # already sets _captured_by_barrier for both protocols), a
            # coordinate/"direct landing" capture (rule 47) only exists on
            # this cop_v1 wire -- nothing else ever tells the main loop to
            # stop. Without this, a confirmed capture leaves the loop
            # advancing to the next round and blocking forever on
            # round_exchange.wait_for_reveal for a reveal the Cop -- who
            # correctly already ended her own match -- will never send.
            self._context._captured_by_landing = True
        self.peer_trace.record_capture_claim(
            claimed_at_step=claimed_at_step,
            thief_row=thief_row,
            thief_col=thief_col,
            cop_row=cop_row,
            cop_col=cop_col,
            confirmed=confirmed,
        )
        cop_send_capture_response(self._context.transport, confirmed, my_row, my_col)
        return {"acknowledged": True}

    def handle_receive_capture_response(
        self, confirmed: bool, true_thief_col: int, true_thief_row: int
    ) -> dict:
        self.peer_trace.record_capture_response(
            confirmed=confirmed, true_thief_row=true_thief_row, true_thief_col=true_thief_col
        )
        return {"acknowledged": True}

    def handle_receive_final_reveal(self, nonces: dict, intents: dict) -> dict:
        """Ch.5.3.2 Final Reveal: store nonces, audit her commits (rules
        19/36), signal shutdown-grace waiters, return the audit summary."""
        self.peer_trace.record_final_reveal(nonces, intents)
        config = self._context.config
        self.opponent_audit = audit_cop_peer_trace(
            self.peer_trace,
            cop_start=config.require("board_and_agents.cop_start"),
            grid_size=int(config.require("board_and_agents.grid_size")),
        )
        self.final_reveal_received.set()
        return {"acknowledged": True, **self.opponent_audit}

    def handle_receive_step0(self, declaration: dict, signature: str, repos: dict) -> dict:
        my_declaration = build_own_declaration(
            self._context.config,
            self._context.group_name,
            self._sub_game_number,
            self._shared_config_path,
        )
        my_signature = sign_cop_declaration(my_declaration)
        verify_their_declaration(declaration, signature, my_declaration)
        return {
            "declaration": my_declaration,
            "signature": my_signature,
            "repos": dict(self._context.repos),
        }
