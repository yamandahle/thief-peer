"""PeerContextMixin: the `infra/mcp_server.py` context handlers
(`handle_negotiate`/`handle_receive_control`/`handle_commit_move`/
`handle_reveal_move`/`handle_get_revealed_records`/
`handle_receive_barrier_declaration`/`handle_receive_capture_claim`), split
out of `peer/runtime.py` to stay under this codebase's file-length
convention -- same reasoning as `peer/round_loop.py`/`peer/match_end.py`. A
mixin, not free functions, since every handler here genuinely needs
`PeerRuntime`'s own state (`round_exchange`, `config`, `group_name`,
`records`, `_match_over`, `state`, `board`), not just a couple of explicit
parameters.

`handle_receive_barrier_declaration`/`handle_receive_capture_claim` close
rules 21/22/46's gap (found in a compliance re-audit against the book's
Appendix E): `domain/rules.py::is_captured_by_barrier` was built and
unit-tested but had zero call sites in the live match loop, since there
was no wire channel for the Cop to ever tell this peer a barrier landed.
The book gives no prescribed wire shape for this (confirmed against the
Cop repo's own `WIRE-CONTRACT.md`, which independently reached the same
conclusion); this repo's own choice, not dictated by anything external --
worth reconciling with the Cop side's shape later, not unilaterally now.
`handle_receive_capture_claim` only ever confirms a claim this peer has
already independently, locally verified (never trusts an unverified
claim at face value) -- rule 22 (never falsely declare a capture) is the
*claimant's* obligation; this is this peer's own defense against a false
claim, from the other side.

`handle_receive_barrier_declaration` also enforces the negotiated
`max_barriers` quota at runtime (docs/TodoCloseGaps.md #3) -- the
Step-0 negotiation already refuses to *start* a match over a config
mismatch, but can't catch a peer who agreed to the quota and then
exceeds it mid-match.
"""

from thief_peer.domain.crypto import hash_config_file
from thief_peer.domain.negotiation import Negotiation, canonical_terms
from thief_peer.domain.rules import is_captured_by_barrier, is_captured_by_stuck
from thief_peer.exceptions import SimulationError
from thief_peer.peer.sealing import sealed_spec_record


class PeerContextMixin:
    def handle_negotiate(self, payload: dict) -> dict:
        # PRD_10 fix (rule 11 [FATAL]): the responder's reply needs its own
        # config_sha256 too, or the initiator's verify_peer only ever has
        # its own half of the byte-identical check to compare against.
        config_sha256 = hash_config_file(self.shared_config_path) if self.shared_config_path else None
        return Negotiation.signed(canonical_terms(self.config), config_sha256=config_sha256)

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

    def handle_receive_barrier_declaration(self, payload: dict) -> dict:
        # docs/TodoCloseGaps.md #3: negotiation already refuses to start a
        # match if the peer's own configured max_barriers disagrees with
        # ours (domain/negotiation.py::Negotiation.verify_peer's generic
        # term comparison; cop_v1's config_sha256 whole-file hash implies
        # the same). What negotiation can't catch is an opponent who
        # agreed to the quota at Step-0 and then exceeds it mid-match --
        # a genuinely new distinct cell that would push the known count
        # past the negotiated ceiling is refused here instead of silently
        # accepted.
        cell = (payload["row"], payload["col"])
        max_barriers = self.config.require("movement_and_barriers.max_barriers")
        if len(self.state.known_barriers | {cell}) > max_barriers:
            raise SimulationError(
                f"Opponent declared barrier {cell} beyond the negotiated "
                f"max_barriers={max_barriers} quota"
            )
        self.state.record_barrier(cell)
        if is_captured_by_barrier(self.state, cell):
            self._captured_by_barrier = True
        return {"ok": True}

    def handle_receive_capture_claim(self, payload: dict) -> dict:
        reason = payload.get("reason")
        if reason == "barrier":
            confirmed = self._captured_by_barrier
        elif reason == "stuck":
            confirmed = is_captured_by_stuck(self.state, self.board)
        else:
            confirmed = False
        return {"confirmed": confirmed}
