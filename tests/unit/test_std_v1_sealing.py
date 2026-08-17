"""interop/std_v1/sealing.py tests."""

from thief_peer.interop.std_v1.sealing import (
    build_audit_record,
    build_turn_message,
    build_turn_payload,
    seal_turn,
    verify_record,
)


def _payload(**overrides):
    base = {
        "step": 1, "sender": "thief", "move": "N", "hint": "cold", "smell_grid": {"3,3": 0.9},
        "barrier_placed": None, "capture_claim": None, "claim_response": None, "win_claim": None,
    }
    base.update(overrides)
    return build_turn_payload(**base)


def test_seal_turn_produces_a_verifiable_commit():
    payload = _payload()
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])
    assert verify_record(record, sealed["commit"]) is True


def test_verify_record_fails_on_a_tampered_move():
    # The whole point of hiding `move`: a player can't silently rewrite
    # what it actually played after the fact.
    payload = _payload(move="N")
    sealed = seal_turn(payload)
    tampered_record = build_audit_record({**payload, "move": "S"}, sealed["nonce"])
    assert verify_record(tampered_record, sealed["commit"]) is False


def test_verify_record_fails_on_a_tampered_public_field():
    payload = _payload()
    sealed = seal_turn(payload)
    tampered_record = build_audit_record({**payload, "hint": "tampered"}, sealed["nonce"])
    assert verify_record(tampered_record, sealed["commit"]) is False


def test_verify_record_fails_with_no_nonce():
    payload = _payload()
    sealed = seal_turn(payload)
    assert verify_record({**payload}, sealed["commit"]) is False


def test_build_turn_message_never_leaks_the_move():
    payload = _payload(move="E")
    sealed = seal_turn(payload)
    message = build_turn_message(payload, sealed["commit"])
    assert "move" not in message


def test_build_turn_message_carries_the_public_fields_commit_and_timestamp():
    payload = _payload()
    sealed = seal_turn(payload)
    message = build_turn_message(payload, sealed["commit"])
    assert message["commit"] == sealed["commit"]
    assert "timestamp" in message
    assert message["step"] == 1
    assert message["sender"] == "thief"
    assert message["hint"] == "cold"


def test_build_audit_record_reveals_the_move():
    payload = _payload(move="STAY")
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])
    assert record["move"] == "STAY"
    assert record["nonce"] == sealed["nonce"]


def test_optional_fields_round_trip_through_the_record():
    payload = _payload(
        step=4, sender="police", move="STAY",
        barrier_placed=[1, 1], capture_claim=[3, 3],
        claim_response={"claim": [3, 3], "caught": False},
    )
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"])
    assert verify_record(record, sealed["commit"]) is True
    assert record["barrier_placed"] == [1, 1]
    assert record["capture_claim"] == [3, 3]
