"""register_cop_tools: attaches `CopContextAdapter`'s handlers
(`cop_server_tools.py`) onto an already-constructed FastMCP instance under
her exact tool names -- split out once `cop_server_tools.py` crossed the
150-line house cap.
"""

import contextlib

from fastmcp import FastMCP

from thief_peer.interop.cop_server_tools import CopContextAdapter

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
    def receive_commit(h_commit: str, sent_at: float, deadline_at: float) -> dict:
        # sent_at/deadline_at (her PRD 15, ch.8.4): the caller's own declared
        # request timing -- her own receive_commit docstring says this is
        # "logged by the callback, never trusted (rule 9)"; accepted here
        # only so her real send_commit's wire shape validates, never used
        # for anything on this side either.
        return adapter.handle_receive_commit(h_commit)

    @mcp.tool
    def receive_reveal(move: dict, hint_text: str, sent_at: float, deadline_at: float) -> dict:
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
    def receive_final_reveal(nonces: dict, intents: dict) -> dict:
        return adapter.handle_receive_final_reveal(nonces, intents)

    @mcp.tool
    def receive_step0(declaration: dict, signature: str, repos: dict) -> dict:
        return adapter.handle_receive_step0(declaration, signature, repos)
