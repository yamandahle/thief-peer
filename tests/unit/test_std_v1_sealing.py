"""interop/std_v1/sealing.py tests: `move` is hidden -- committed into
the hash but never sent live in the turn message (spec Appendix D has no
`move` field at all) -- and verify_record must actually catch a tampered
revealed record, not just echo it back."""

from thief_peer.interop.std_v1.sealing import (
    _HIDDEN_FIELDS,
    _PUBLIC_FIELDS,
    build_audit_record,
    build_turn_message,
    build_turn_payload,
    seal_turn,
    verify_record,
)


def _payload(**overrides):
    base = dict(
        step=1,
        sender="thief",
        move="N",
        hint="cold",
        smell_grid={"3,3": 0.9},
        barrier_placed=None,
        capture_claim=None,
        claim_response=None,
        win_claim=None,
    )
    base.update(overrides)
    return build_turn_payload(
        step=base["step"], sender=base["sender"], move=base["move"], hint=base["hint"],
        smell_grid=base["smell_grid"], barrier_placed=base["barrier_placed"],
        capture_claim=base["capture_claim"], claim_response=base["claim_response"],
        win_claim=base["win_claim"],
    )


def test_move_is_hidden_from_the_live_turn_message():
    payload = _payload()
    sealed = seal_turn(payload)
    message = build_turn_message(payload, sealed["commit"])
    assert "move" not in message
    assert set(_PUBLIC_FIELDS) <= set(message)
    assert message["commit"] == sealed["commit"]


def test_move_is_present_in_the_revealed_audit_record():
    payload = _payload(move="E")
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"], sealed["commit"])
    assert record["payload"]["move"] == "E"
    assert record["nonce"] == sealed["nonce"]


def test_build_audit_record_uses_the_kit_pinned_nested_shape():
    # Reconciled live against yanell11: their own reference auditor reads
    # record["payload"], not the record's own top-level keys -- a flat
    # record fails every audit against a peer expecting this nesting.
    payload = _payload()
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"], sealed["commit"])
    assert set(record.keys()) == {"payload", "nonce", "commit"}
    assert record["commit"] == sealed["commit"]
    assert record["payload"] == payload


def test_verify_record_accepts_an_honest_record():
    payload = _payload()
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"], sealed["commit"])
    assert verify_record(record, sealed["commit"]) is True


def test_verify_record_rejects_a_record_with_a_tampered_hidden_field():
    payload = _payload(move="N")
    sealed = seal_turn(payload)
    tampered_record = build_audit_record(payload, sealed["nonce"], sealed["commit"])
    tampered_record["payload"]["move"] = "S"  # peer claims a different move than it committed to
    assert verify_record(tampered_record, sealed["commit"]) is False


def test_verify_record_rejects_a_record_missing_its_nonce():
    payload = _payload()
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"], sealed["commit"])
    del record["nonce"]
    assert verify_record(record, sealed["commit"]) is False


def test_verify_record_rejects_a_record_missing_its_payload():
    payload = _payload()
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"], sealed["commit"])
    del record["payload"]
    assert verify_record(record, sealed["commit"]) is False


def test_hidden_fields_contains_only_move():
    assert _HIDDEN_FIELDS == ("move",)
