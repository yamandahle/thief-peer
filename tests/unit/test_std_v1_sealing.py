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


def test_verify_record_accepts_a_peers_own_differently_shaped_payload():
    # A real cross-team peer's kit is free to seal a payload with entirely
    # different field names than ours -- verify_record must re-hash
    # whatever it actually received, not assume our own schema. These are
    # yanell11's own real records (live match), reproduced verbatim.
    record = {
        "payload": {
            "hint": "Somewhere between Mount Carmel and nowhere, good luck.",
            "intent": "truth", "move": "move:E", "position": [0, 1], "role": "police",
            "state": "grid=7x7;self=[0, 1];barriers=[]", "step": 1,
            "tokens_step": 0, "tokens_total": 0, "type": "turn",
        },
        "nonce": "bc853589450320c7891fc33889bdc7a9",
    }
    expected_commit = "6b59c1f71ff064b542eadeb9d393319d8a1a905b50d7c4ab2be41f61080447a6"
    assert verify_record(record, expected_commit) is True


def test_verify_record_rejects_a_record_missing_its_payload():
    payload = _payload()
    sealed = seal_turn(payload)
    record = build_audit_record(payload, sealed["nonce"], sealed["commit"])
    del record["payload"]
    assert verify_record(record, sealed["commit"]) is False


def test_hidden_fields_contains_only_move():
    assert _HIDDEN_FIELDS == ("move",)
