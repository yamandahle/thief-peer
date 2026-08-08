"""NullPeerContext: a context that structurally cannot answer any of the
live-match tools -- for callers (the smoke-test diagnostic, ping/
submit_audit-only tests) that were never meant to play a real match and
only need the older tools. Fails loudly rather than silently no-opping if
ever called. Split out of `infra/mcp_server.py` to stay under this
codebase's file-length convention.
"""


class NullPeerContext:
    def handle_negotiate(self, payload: dict) -> dict:
        raise NotImplementedError("NullPeerContext cannot negotiate a real match")

    def handle_receive_control(self, payload: dict) -> dict:
        raise NotImplementedError("NullPeerContext cannot exchange Step-0")

    def handle_commit_move(self, payload: dict) -> dict:
        raise NotImplementedError("NullPeerContext cannot receive a commit")

    def handle_reveal_move(self, payload: dict) -> dict:
        raise NotImplementedError("NullPeerContext cannot receive a reveal")

    def handle_get_revealed_records(self, payload: dict) -> dict:
        raise NotImplementedError("NullPeerContext cannot reveal records")

    def handle_receive_barrier_declaration(self, payload: dict) -> dict:
        raise NotImplementedError("NullPeerContext cannot receive a barrier declaration")

    def handle_receive_capture_claim(self, payload: dict) -> dict:
        raise NotImplementedError("NullPeerContext cannot receive a capture claim")
