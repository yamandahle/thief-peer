"""turn_sender (PRD_8 §3): builds the book's two separate per-round
messages via domain/protocol.py and sends each through the opponent
transport -- the hash-only Commit first, the move+hint+scent Reveal later
(never bundled), matching Figure 6 exactly.
"""

from thief_peer.domain.protocol import build_commit_message, build_reveal_message


def send_commit(transport, step: int, sender: str, sealed: dict) -> dict:
    message = build_commit_message(step, sender, sealed["commit"])
    return transport.call("commit_move", {"payload": message})


def send_reveal(transport, step: int, sender: str, decision, scent_snapshot: dict) -> dict:
    move = decision.direction.value if decision.direction else "STAY"
    message = build_reveal_message(
        step, sender, decision.hint, scent_snapshot, move, decision.verdict
    )
    return transport.call("reveal_move", {"payload": message})
