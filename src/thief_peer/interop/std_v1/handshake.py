"""Mutual negotiation handshake (spec Section 3). Push-based and
idempotent, not a single request/response RPC: this side keeps re-sending
its own unchanged offer to the peer's `negotiate` tool while waiting for
the peer's own matching offer to land on `exchange` (fed independently by
this side's own `negotiate` tool handler, called by the peer on its own
schedule) -- Section 3's own "a single successful negotiate call MUST NOT
be treated as a completed handshake" requirement.
"""

from __future__ import annotations

import time

from thief_peer.exceptions import DeadlineExceededError, SimulationError
from thief_peer.interop.std_v1.crypto import commit_of, derive_game_uid, fresh_nonce
from thief_peer.interop.std_v1.terms import validate_terms
from thief_peer.interop.std_v1.wire import send_negotiate


def build_offer(
    terms: dict,
    group_id: str,
    role: str,
    sub_game_number: int,
    identity: dict,
    game_uid: str,
    nonce: str,
) -> dict:
    return {
        "terms": terms,
        "nonce": nonce,
        "signature": commit_of(terms, nonce),
        "group_id": group_id,
        "role": role,
        "sub_game_number": sub_game_number,
        "identity": identity,
        "game_uid": game_uid,
    }


def validate_offer(offer: dict, my_terms: dict) -> None:
    """Section 3's own greeting-validation rules 1-4 -- rules 5/6 (missing
    group_id, mismatched game_uid) are checked by the caller, which alone
    knows the expected game_uid for this pairing."""
    terms = offer.get("terms")
    validate_terms(terms)
    if terms != my_terms:
        raise SimulationError("peer's terms differ from ours -- refusing the greeting (rule 3)")
    nonce = offer.get("nonce")
    signature = offer.get("signature")
    if not nonce or not signature:
        raise SimulationError("greeting missing nonce/signature (rule 4)")
    if commit_of(terms, nonce) != signature:
        raise SimulationError("greeting signature does not verify against its own terms (rule 4)")
    if not offer.get("group_id"):
        raise SimulationError("greeting missing group_id (rule 5)")


def negotiate_sub_game(
    transport,
    exchange,
    my_terms: dict,
    my_group_id: str,
    their_group_id: str,
    role: str,
    sub_game_number: int,
    identity: dict,
    resend_interval_sec: float = 2.0,
    ceiling_sec: float = 300.0,
) -> dict:
    """Sends this side's own offer, then repeatedly re-sends the identical
    offer (same nonce/terms/identity, never regenerated on a retry -- the
    spec's own explicit requirement) while polling `exchange` for the
    peer's matching one, until either it arrives or `ceiling_sec` elapses.
    Returns the peer's own validated offer."""
    game_uid = derive_game_uid(my_terms, my_group_id, their_group_id)
    nonce = fresh_nonce()
    my_offer = build_offer(my_terms, my_group_id, role, sub_game_number, identity, game_uid, nonce)

    deadline = time.monotonic() + ceiling_sec
    while time.monotonic() < deadline:
        send_negotiate(transport, my_offer)
        remaining = deadline - time.monotonic()
        try:
            their_offer = exchange.wait_for_offer(sub_game_number, timeout=min(resend_interval_sec, max(0.0, remaining)))
        except DeadlineExceededError:
            continue  # re-send the identical offer, never regenerated
        validate_offer(their_offer, my_terms)
        declared_uid = their_offer.get("game_uid")
        if declared_uid != game_uid:
            raise SimulationError(
                f"peer's declared game_uid {declared_uid!r} != derived {game_uid!r} (rule 6)"
            )
        return their_offer

    raise DeadlineExceededError(
        f"no matching negotiation offer for sub_game {sub_game_number} within {ceiling_sec}s"
    )
