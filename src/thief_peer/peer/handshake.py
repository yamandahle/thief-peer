"""Pre-game handshake (PRD_6 §2.5, §3): exchanges the negotiation signature
then the sealed Step-0 declaration, both complete before move 1 (`PLAN.md`'s
turn FSM `NEGOTIATING` state). Works over any `transport` exposing
`.call(tool_name, payload) -> dict`, so it can run against a real MCP peer
or (as tested) a simulated one -- `PeerRuntime` wires this into the real
turn loop in a later stage.

`shared_config_path` (PRD_10 fix, rule 11 [FATAL]) is optional and, when
given, adds a byte-identical file-hash check alongside the term-by-term one
`Negotiation.verify_peer` already did -- see `domain/negotiation.py`'s own
docstring for why the weaker check alone isn't enough. `None` (the default)
preserves every existing caller's behavior exactly.
"""

from thief_peer.domain.crypto import hash_config_file
from thief_peer.domain.negotiation import Negotiation, canonical_terms
from thief_peer.peer.sealing import sealed_spec_record
from thief_peer.shared.config import ConfigManager


def run_handshake(
    config: ConfigManager,
    transport,
    group_name: str,
    shared_config_path: str | None = None,
) -> dict:
    my_terms = canonical_terms(config)
    my_config_sha256 = hash_config_file(shared_config_path) if shared_config_path else None
    my_negotiation = Negotiation.signed(my_terms, config_sha256=my_config_sha256)

    their_negotiation = transport.call("negotiate", my_negotiation)
    Negotiation.verify_peer(
        their_negotiation["terms"],
        their_negotiation["nonce"],
        their_negotiation["commit"],
        my_terms,
        their_negotiation["scent_lock_hash"],
        my_config_sha256=my_config_sha256,
        their_config_sha256=their_negotiation.get("config_sha256"),
    )

    my_spec = sealed_spec_record(group_name)
    their_step0 = transport.call("receive_control", {"type": "step0", "record": my_spec})
    return their_step0["record"]
