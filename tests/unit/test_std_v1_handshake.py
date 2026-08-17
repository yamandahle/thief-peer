"""interop/std_v1/handshake.py tests: mutual, idempotent negotiation
(spec Section 3) -- a single successful negotiate call must never be
treated as a completed handshake, so negotiate_sub_game keeps resending
the identical offer while polling the exchange for the peer's own."""

import pytest

from thief_peer.exceptions import DeadlineExceededError, SimulationError
from thief_peer.interop.std_v1.crypto import commit_of, derive_game_uid
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.handshake import build_offer, negotiate_sub_game, validate_offer

_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "min_center_intensity": 0.5,
    "max_steps": 35,
    "barriers_max": 14,
    "setting": "Haifa",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
    "num_games": 6,
}


class _StubTransport:
    def __init__(self):
        self.calls = 0

    def call(self, name, payload):
        self.calls += 1
        return {"acknowledged": True}


def test_build_offer_signs_terms_with_the_given_nonce():
    offer = build_offer(_TERMS, "us", "thief", 1, {"group_id": "us"}, "uid-1", "nonce-1")
    assert offer["signature"] == commit_of(_TERMS, "nonce-1")
    assert offer["game_uid"] == "uid-1"


def test_validate_offer_accepts_a_well_formed_matching_offer():
    offer = build_offer(_TERMS, "peer", "police", 1, {}, "uid-1", "nonce-1")
    validate_offer(offer, _TERMS)  # must not raise


def test_validate_offer_rejects_mismatched_terms():
    different_terms = {**_TERMS, "board_size": 8}
    offer = build_offer(different_terms, "peer", "police", 1, {}, "uid-1", "nonce-1")
    with pytest.raises(SimulationError, match="differ from ours"):
        validate_offer(offer, _TERMS)


def test_validate_offer_rejects_a_forged_signature():
    offer = build_offer(_TERMS, "peer", "police", 1, {}, "uid-1", "nonce-1")
    offer["signature"] = "0" * 64
    with pytest.raises(SimulationError, match="does not verify"):
        validate_offer(offer, _TERMS)


def test_validate_offer_rejects_a_missing_group_id():
    offer = build_offer(_TERMS, "peer", "police", 1, {}, "uid-1", "nonce-1")
    offer["group_id"] = ""
    with pytest.raises(SimulationError, match="group_id"):
        validate_offer(offer, _TERMS)


def test_negotiate_sub_game_returns_the_peers_matching_offer_once_it_lands():
    exchange = StdExchange(poll_interval=0.01)
    transport = _StubTransport()
    game_uid = derive_game_uid(_TERMS, "us", "peer")
    peer_offer = build_offer(_TERMS, "peer", "police", 1, {"identity": "peer"}, game_uid, "peer-nonce")
    exchange.record_offer(peer_offer)

    result = negotiate_sub_game(
        transport, exchange, _TERMS, "us", "peer", "thief", 1, {},
        resend_interval_sec=0.01, ceiling_sec=1.0,
    )
    assert result == peer_offer
    assert transport.calls >= 1


def test_negotiate_sub_game_rejects_a_peer_offer_with_the_wrong_game_uid():
    exchange = StdExchange(poll_interval=0.01)
    transport = _StubTransport()
    bad_offer = build_offer(_TERMS, "peer", "police", 1, {}, "totally-wrong-uid", "peer-nonce")
    exchange.record_offer(bad_offer)

    with pytest.raises(SimulationError, match="game_uid"):
        negotiate_sub_game(
            transport, exchange, _TERMS, "us", "peer", "thief", 1, {},
            resend_interval_sec=0.01, ceiling_sec=1.0,
        )


def test_negotiate_sub_game_raises_deadline_exceeded_if_the_peer_never_answers():
    exchange = StdExchange(poll_interval=0.01)
    transport = _StubTransport()
    with pytest.raises(DeadlineExceededError):
        negotiate_sub_game(
            transport, exchange, _TERMS, "us", "peer", "thief", 1, {},
            resend_interval_sec=0.01, ceiling_sec=0.05,
        )
