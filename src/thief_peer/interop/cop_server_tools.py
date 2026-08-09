"""CopContextAdapter: lets this peer's own FastMCP server also answer a
real Cop client's actual tool calls (`receive_commit`, `receive_reveal`,
`share_scent_map`, `receive_step0`, `receive_barrier_declaration`,
`receive_capture_claim`, `receive_capture_response`, `receive_final_reveal`)
-- registered by `cop_server_registration.py::register_cop_tools` alongside
the native tools (`infra/mcp_server.py`), sharing the same underlying game
state via `context` (normally `PeerRuntime` itself); only the entry
translation differs.

Step tracking: her wire messages carry no explicit step number (unlike
this repo's own `commit_move`/`reveal_move` payloads) -- she relies on
call order matching turn order, so this adapter does too, via its own
independent counters. A deliberate, documented simplification (per-
adapter, not coupled to the live round loop's own step variable) -- correct
for a normal, synchronous, one-call-at-a-time match, not hardened against
retries or out-of-order delivery.

`handle_receive_capture_claim` acknowledges receipt only, matching her own
`receive_capture_claim` contract ("the truthful confirm/deny travels back
later, as its own commit, via receive_capture_response, not this call's
return value") -- actually firing that follow-up `receive_capture_response`
call back to her is not wired here (would need an outbound transport
reference inside an inbound handler); a known, flagged gap, not an
oversight.

`handle_receive_final_reveal` was found missing by an actual live run
against her real process, not by inspection: her own `report_game()`
always calls this peer's `receive_final_reveal` as part of *her* end-of-
game sequence, regardless of whether this side's own `finalize_match`
skips the (incompatible) audit exchange in `cop_v1` mode -- omitting the
tool entirely meant her side's own match, otherwise fully successful,
crashed on its very last step. Acknowledges only; no audit is attempted
against the nonces/intents (interop/__init__.py's documented boundary).
"""

import threading

from thief_peer.interop.cop_handshake import build_own_declaration, verify_their_declaration
from thief_peer.interop.cop_wire import serialize_scent_for_cop, sign_cop_declaration


class CopContextAdapter:
    def __init__(self, context, shared_config_path: str, sub_game_number: int = 1):
        self._context = context
        self._shared_config_path = shared_config_path
        self._sub_game_number = sub_game_number
        self._commit_step = 0
        # Set once her own receive_final_reveal call actually lands -- lets
        # cop_shutdown_grace wait for the real event rather than guessing a
        # fixed sleep duration (her round loop's own pace isn't ours to
        # predict; a live run against her real process is exactly what
        # showed a blind 5s sleep wasn't long enough).
        self.final_reveal_received = threading.Event()
        self._reveal_step = 0

    def handle_receive_commit(self, h_commit: str) -> dict:
        self._context.handle_commit_move({"step": self._commit_step, "h_commit": h_commit})
        self._commit_step += 1
        return {"acknowledged": True}

    def handle_receive_reveal(self, move: dict, hint_text: str) -> dict:
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
        self._reveal_step += 1
        return {"accepted": True, "word_count": len(hint_text.split())}

    def handle_share_scent_map(self) -> dict:
        return serialize_scent_for_cop(self._context.scent.snapshot())

    def handle_receive_barrier_declaration(self, col: int, row: int) -> dict:
        return self._context.handle_receive_barrier_declaration({"row": row, "col": col})

    def handle_receive_capture_claim(
        self, thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        return {"acknowledged": True}

    def handle_receive_capture_response(
        self, confirmed: bool, true_thief_col: int, true_thief_row: int
    ) -> dict:
        return {"acknowledged": True}

    def handle_receive_final_reveal(self, nonces: dict, intents: dict) -> dict:
        self.final_reveal_received.set()
        return {"acknowledged": True}

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
