"""PeerContextMixin: the `infra/mcp_server.py` context handlers
(`handle_negotiate`/`handle_receive_control`/`handle_commit_move`/
`handle_reveal_move`/`handle_get_revealed_records`), split out of
`peer/runtime.py` to stay under this codebase's file-length convention --
same reasoning as `peer/round_loop.py`/`peer/match_end.py`. A mixin, not
free functions, since every handler here genuinely needs `PeerRuntime`'s
own state (`round_exchange`, `config`, `group_name`, `records`,
`_match_over`), not just a couple of explicit parameters.
"""

from thief_peer.domain.negotiation import Negotiation, canonical_terms
from thief_peer.exceptions import SimulationError
from thief_peer.peer.sealing import sealed_spec_record


class PeerContextMixin:
    def handle_negotiate(self, payload: dict) -> dict:
        return Negotiation.signed(canonical_terms(self.config))

    def handle_receive_control(self, payload: dict) -> dict:
        if payload.get("type") == "step0":
            return {"record": sealed_spec_record(self.group_name)}
        raise SimulationError(f"Unsupported control message type: {payload.get('type')}")

    def handle_commit_move(self, payload: dict) -> dict:
        self.round_exchange.record_commit(payload["step"], payload["h_commit"])
        return {"ok": True}

    def handle_reveal_move(self, payload: dict) -> dict:
        self.round_exchange.record_reveal(payload["step"], payload)
        return {"ok": True}

    def handle_get_revealed_records(self, payload: dict) -> dict:
        # Rule 18: the nonce stays secret until the game ends -- refuse to
        # answer this pull before *this* peer has itself decided the match
        # is over, regardless of how confident the caller sounds.
        if not self._match_over:
            raise SimulationError("Records are not revealed until the match has ended (rule 18)")
        return {"records": self.records}
