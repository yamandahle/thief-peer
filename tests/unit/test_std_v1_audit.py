"""interop/std_v1/audit.py tests: per-sub-game mutual audit and final
series-consensus exchange (spec Sections 9-11). verify_peer_records is
the security-critical one -- it must check a peer's revealed record
against the commit *this side actually saw live*, never against a commit
the record merely claims for itself."""

import pytest

from thief_peer.exceptions import DeadlineExceededError, SimulationError, TransportError
from thief_peer.interop.std_v1.audit import (
    build_audit_envelope,
    build_consensus_envelope,
    build_consensus_object,
    build_sub_game_row,
    confirm_agreement,
    send_and_await,
    validate_consensus_envelope,
    verify_peer_records,
)
from thief_peer.interop.std_v1.sealing import build_audit_record, build_turn_payload, seal_turn


def _sealed_record(step: int, move: str):
    payload = build_turn_payload(
        step=step, sender="thief", move=move, hint="", smell_grid={},
        barrier_placed=None, capture_claim=None, claim_response=None, win_claim=None,
    )
    sealed = seal_turn(payload)
    return build_audit_record(payload, sealed["nonce"], sealed["commit"]), sealed["commit"]


def test_verify_peer_records_all_clean_when_records_match_seen_commits():
    record, commit = _sealed_record(1, "N")
    result = verify_peer_records([record], {1: commit})
    assert result == {"log_verified": True, "tampered": False, "mismatched_steps": []}


def test_verify_peer_records_catches_a_record_rewritten_after_the_fact():
    record, commit = _sealed_record(1, "N")
    record["payload"]["move"] = "S"  # peer reveals a different move than the commit it sent live
    result = verify_peer_records([record], {1: commit})
    assert result["log_verified"] is False
    assert result["tampered"] is True
    assert result["mismatched_steps"] == [1]


def test_verify_peer_records_rejects_a_record_for_a_step_we_never_saw_a_commit_for():
    record, _real_commit = _sealed_record(5, "E")
    result = verify_peer_records([record], {})  # no commit was ever seen live for step 5
    assert result["tampered"] is True
    assert result["mismatched_steps"] == [5]


def test_verify_peer_records_never_trusts_a_commit_the_record_claims_for_itself():
    # A malicious peer could stash a fabricated "commit" field on its own
    # record -- verify_peer_records must ignore it entirely and only ever
    # compare against peer_commits (what we actually saw live).
    record, commit = _sealed_record(1, "N")
    record["commit"] = "forged-not-a-real-commit"
    result = verify_peer_records([record], {1: commit})
    assert result["log_verified"] is True  # still verifies against the real commit we saw


def test_build_sub_game_row_has_exactly_the_five_spec_keys():
    row = build_sub_game_row(2, "capture", {"A": "police", "B": "thief"}, {"A": 20, "B": 5}, "A")
    assert set(row) == {"sub_game_number", "result", "roles", "score", "winner_group"}


def test_build_consensus_object_sorts_rows_by_ascending_sub_game_number():
    rows = [build_sub_game_row(3, "survival", {}, {}, None), build_sub_game_row(1, "capture", {}, {}, None)]
    obj = build_consensus_object("A-vs-B", "uid", rows)
    assert [row["sub_game_number"] for row in obj["sub_games"]] == [1, 3]
    assert obj == {"game_id": "A-vs-B", "game_uid": "uid", "sub_games": obj["sub_games"]}


def test_validate_consensus_envelope_accepts_a_well_formed_envelope():
    envelope = build_consensus_envelope("thief", "a" * 64)
    assert validate_consensus_envelope(envelope) == "a" * 64


def test_validate_consensus_envelope_rejects_wrong_result_claim():
    with pytest.raises(SimulationError):
        validate_consensus_envelope({"sender": "thief", "records": [], "consensus_sha": "a" * 64, "result_claim": "capture"})


def test_validate_consensus_envelope_rejects_a_non_empty_records_list():
    with pytest.raises(SimulationError):
        validate_consensus_envelope(
            {"sender": "thief", "records": [{"step": 1}], "consensus_sha": "a" * 64, "result_claim": "series_consensus"}
        )


def test_validate_consensus_envelope_rejects_a_malformed_digest():
    with pytest.raises(SimulationError):
        validate_consensus_envelope(
            {"sender": "thief", "records": [], "consensus_sha": "not-hex", "result_claim": "series_consensus"}
        )


def test_validate_consensus_envelope_rejects_an_unknown_sender_role():
    with pytest.raises(SimulationError):
        validate_consensus_envelope(
            {"sender": "referee", "records": [], "consensus_sha": "a" * 64, "result_claim": "series_consensus"}
        )


def test_confirm_agreement_requires_all_four_conditions():
    assert confirm_agreement(True, True, "x", "x") is True
    assert confirm_agreement(False, True, "x", "x") is False
    assert confirm_agreement(True, False, "x", "x") is False
    assert confirm_agreement(True, True, "x", "y") is False


class _StubTransport:
    def __init__(self):
        self.calls = 0

    def call(self, name, payload):
        self.calls += 1
        return {"acknowledged": True}


def test_send_and_await_resends_until_the_wait_fn_returns():
    transport = _StubTransport()
    attempts = {"n": 0}

    def wait_fn(timeout):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise DeadlineExceededError("not yet")
        return {"result_claim": "capture"}

    result = send_and_await(
        transport, wait_fn, build_audit_envelope("thief", [], "capture", 1),
        resend_interval_sec=0.01, ceiling_sec=1.0,
    )
    assert result == {"result_claim": "capture"}
    assert transport.calls == 3


def test_send_and_await_retries_through_a_transient_transport_error():
    # submit_audit is idempotent (spec Section 7), so a transient failure
    # (peer's tunnel briefly down) must be retried, never fatal.
    class _FlakyTransport:
        def __init__(self):
            self.calls = 0

        def call(self, name, payload):
            self.calls += 1
            if self.calls < 3:
                raise TransportError("502 Bad Gateway")
            return {"acknowledged": True}

    transport = _FlakyTransport()

    def wait_fn(timeout):
        return {"result_claim": "capture"}

    result = send_and_await(
        transport, wait_fn, build_audit_envelope("thief", [], "capture", 1),
        resend_interval_sec=0.01, ceiling_sec=2.0,
    )
    assert result == {"result_claim": "capture"}
    assert transport.calls >= 3


def test_send_and_await_raises_deadline_exceeded_past_the_ceiling():
    transport = _StubTransport()

    def wait_fn(timeout):
        raise DeadlineExceededError("never arrives")

    with pytest.raises(DeadlineExceededError):
        send_and_await(
            transport, wait_fn, build_audit_envelope("thief", [], "capture", 1),
            resend_interval_sec=0.01, ceiling_sec=0.05,
        )
