"""Pre-game handshake (PRD_6 §2.5, §3): exchanges the negotiation signature
then the sealed Step-0 declaration, both complete before move 1 (`PLAN.md`'s
turn FSM `NEGOTIATING` state). Works over any `transport` exposing
`.call(tool_name, payload) -> dict`, so it can run against a real MCP peer
or (as tested) a simulated one -- `PeerRuntime` wires this into the real
turn loop in a later stage.
"""

from thief_peer.domain.negotiation import Negotiation, canonical_terms
from thief_peer.peer.sealing import sealed_spec_record
from thief_peer.shared.config import ConfigManager


def run_handshake(config: ConfigManager, transport, group_name: str) -> dict:
    my_terms = canonical_terms(config)
    my_negotiation = Negotiation.signed(my_terms)

    their_negotiation = transport.call("negotiate", my_negotiation)
    Negotiation.verify_peer(
        their_negotiation["terms"],
        their_negotiation["nonce"],
        their_negotiation["commit"],
        my_terms,
    )

    my_spec = sealed_spec_record(group_name)
    their_step0 = transport.call("receive_control", {"type": "step0", "record": my_spec})
    return their_step0["record"]
