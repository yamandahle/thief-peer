"""interop/std_v1/handshake.py tests -- exercised against a real
StdExchange on "the other side" so this is a genuine mutual exchange, not
just one half in isolation."""

import pytest

from thief_peer.exceptions import DeadlineExceededError, SimulationError
from thief_peer.interop.std_v1.crypto import commit_of, derive_game_uid, fresh_nonce
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.handshake import build_offer, negotiate_sub_game, validate_offer
from thief_peer.interop.std_v1.terms import load_terms

TERMS = load_terms()


class _PeerTransport:
    """Delivers calls directly into the peer's own StdExchange, standing
    in for a real MCP round trip -- mirrors test_handshake.py's own
    _StubPeerTransport pattern for the native protocol."""

    def __init__(self, peer_exchange: StdExchange):
        self._peer_exchange = peer_exchange

    def call(self, tool_name, payload, retryable=True):
        assert tool_name == "negotiate"
        self._peer_exchange.record_offer(payload["message"])
        return {"ok": True}


def test_negotiate_sub_game_returns_the_peers_validated_offer():
    my_exchange = StdExchange(poll_interval=0.01)
    their_exchange = StdExchange(poll_interval=0.01)
    my_transport = _PeerTransport(their_exchange)

    # The peer's own offer, already sitting in my_exchange as if their
    # negotiate tool handler had already recorded it.
    game_uid = derive_game_uid(TERMS, "thief-team", "dev-team")
    their_nonce = fresh_nonce()
    their_offer = build_offer(
        TERMS, "dev-team", "police", 1, {"group_id": "dev-team"}, game_uid, their_nonce
    )
    my_exchange.record_offer(their_offer)

    result = negotiate_sub_game(
        my_transport, my_exchange, TERMS, "thief-team", "dev-team", "thief", 1,
        {"group_id": "thief-team"}, resend_interval_sec=0.05, ceiling_sec=2.0,
    )

    assert result == their_offer
    # Our own offer really was sent to the peer's exchange.
    sent = their_exchange.wait_for_offer(1, timeout=1.0)
    assert sent["group_id"] == "thief-team"
    assert sent["role"] == "thief"


def test_negotiate_sub_game_times_out_when_the_peer_never_answers():
    my_exchange = StdExchange(poll_interval=0.01)
    their_exchange = StdExchange(poll_interval=0.01)
    transport = _PeerTransport(their_exchange)

    with pytest.raises(DeadlineExceededError):
        negotiate_sub_game(
            transport, my_exchange, TERMS, "thief-team", "dev-team", "thief", 1,
            {"group_id": "thief-team"}, resend_interval_sec=0.05, ceiling_sec=0.2,
        )


def test_negotiate_sub_game_rejects_a_mismatched_game_uid():
    my_exchange = StdExchange(poll_interval=0.01)
    their_exchange = StdExchange(poll_interval=0.01)
    transport = _PeerTransport(their_exchange)

    bad_offer = build_offer(
        TERMS, "dev-team", "police", 1, {"group_id": "dev-team"}, "not-the-real-uid", fresh_nonce()
    )
    my_exchange.record_offer(bad_offer)

    with pytest.raises(SimulationError, match="game_uid"):
        negotiate_sub_game(
            transport, my_exchange, TERMS, "thief-team", "dev-team", "thief", 1,
            {"group_id": "thief-team"}, resend_interval_sec=0.05, ceiling_sec=2.0,
        )


def test_validate_offer_rejects_terms_that_differ():
    nonce = fresh_nonce()
    offer = build_offer(
        {**TERMS, "setting": "Tampered"}, "dev-team", "police", 1, {}, "uid", nonce
    )
    with pytest.raises(SimulationError, match="differ"):
        validate_offer(offer, TERMS)


def test_validate_offer_rejects_a_bad_signature():
    offer = build_offer(TERMS, "dev-team", "police", 1, {}, "uid", fresh_nonce())
    offer["signature"] = "0" * 64  # doesn't match commit_of(terms, nonce)
    with pytest.raises(SimulationError, match="signature"):
        validate_offer(offer, TERMS)


def test_validate_offer_rejects_a_missing_group_id():
    offer = build_offer(TERMS, "", "police", 1, {}, "uid", fresh_nonce())
    offer["group_id"] = ""
    with pytest.raises(SimulationError, match="group_id"):
        validate_offer(offer, TERMS)


def test_validate_offer_accepts_a_well_formed_matching_offer():
    nonce = fresh_nonce()
    offer = build_offer(TERMS, "dev-team", "police", 1, {}, "uid", nonce)
    validate_offer(offer, TERMS)  # must not raise


def test_build_offer_signature_matches_commit_of():
    nonce = fresh_nonce()
    offer = build_offer(TERMS, "dev-team", "police", 1, {}, "uid", nonce)
    assert offer["signature"] == commit_of(TERMS, nonce)
