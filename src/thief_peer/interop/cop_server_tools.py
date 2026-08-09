"""CopContextAdapter: lets this peer's own FastMCP server also answer a
real Cop client's actual tool calls (`receive_commit`, `receive_reveal`,
`share_scent_map`, `receive_step0`, `receive_barrier_declaration`,
`receive_capture_claim`, `receive_capture_response`) -- registered
alongside the native tools (`infra/mcp_server.py`), sharing the same
underlying game state via `context` (normally `PeerRuntime` itself); only
the entry translation differs.

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
"""

import contextlib

from fastmcp import FastMCP

from thief_peer.interop.cop_handshake import build_own_declaration, verify_their_declaration
from thief_peer.interop.cop_wire import serialize_scent_for_cop, sign_cop_declaration


class CopContextAdapter:
    def __init__(self, context, shared_config_path: str, sub_game_number: int = 1):
        self._context = context
        self._shared_config_path = shared_config_path
        self._sub_game_number = sub_game_number
        self._commit_step = 0
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


_COLLIDES_WITH_NATIVE = ("receive_barrier_declaration", "receive_capture_claim")


def register_cop_tools(mcp: FastMCP, adapter: CopContextAdapter) -> None:
    """Registers her exact tool names onto an already-constructed `mcp`
    instance, alongside the native Thief tools `infra/mcp_server.py`
    already registered. Two names collide: this repo's own (pre-existing,
    not book-mandated) `receive_barrier_declaration`/`receive_capture_claim`
    tools happen to share her exact names but a different parameter shape
    (`payload: dict` vs her flat `col`/`row`/... kwargs). `mcp.tool` doesn't
    overwrite an existing registration (only warns and keeps the first), so
    the native versions are explicitly removed first -- a `cop_v1` server
    always answers *her* shape for these two, never silently keeps the
    native one underneath."""
    for name in _COLLIDES_WITH_NATIVE:
        # nothing native registered under this name (e.g. a fresh mcp in tests) is fine
        with contextlib.suppress(KeyError):
            mcp.local_provider.remove_tool(name)

    @mcp.tool
    def receive_commit(h_commit: str) -> dict:
        return adapter.handle_receive_commit(h_commit)

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str) -> dict:
        return adapter.handle_receive_reveal(move, hint_text)

    @mcp.tool
    def share_scent_map() -> dict:
        return adapter.handle_share_scent_map()

    @mcp.tool
    def receive_barrier_declaration(col: int, row: int) -> dict:
        return adapter.handle_receive_barrier_declaration(col, row)

    @mcp.tool
    def receive_capture_claim(
        thief_col: int, thief_row: int, cop_col: int, cop_row: int, claimed_at_step: int
    ) -> dict:
        return adapter.handle_receive_capture_claim(
            thief_col, thief_row, cop_col, cop_row, claimed_at_step
        )

    @mcp.tool
    def receive_capture_response(confirmed: bool, true_thief_col: int, true_thief_row: int) -> dict:
        return adapter.handle_receive_capture_response(confirmed, true_thief_col, true_thief_row)

    @mcp.tool
    def receive_step0(declaration: dict, signature: str, repos: dict) -> dict:
        return adapter.handle_receive_step0(declaration, signature, repos)
