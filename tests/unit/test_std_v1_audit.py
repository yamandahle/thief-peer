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
    peer_github_commit,
    send_and_await,
    turn_records_only,
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


def test_turn_records_only_drops_a_system_spec_record():
    turn_record, _ = _sealed_record(1, "N")
    system_spec_record = {"payload": {"type": "system_spec", "step": 0}, "nonce": "n", "commit": "c"}
    assert turn_records_only([system_spec_record, turn_record]) == [turn_record]


def test_turn_records_only_keeps_a_real_step_0_turn_record():
    # Only the declared type, never the step number itself, decides what
    # gets filtered -- a peer numbering turns from 0 must still be caught
    # by verify_peer_records if it fabricates one.
    turn_record, _ = _sealed_record(0, "N")
    assert turn_records_only([turn_record]) == [turn_record]


def test_peer_github_commit_reads_it_off_the_system_spec_record():
    record = {"payload": {"type": "system_spec", "step": 0, "github_commit": "a" * 40}, "nonce": "n", "commit": "c"}
    assert peer_github_commit([record]) == "a" * 40


def test_peer_github_commit_none_when_no_system_spec_record_present():
    turn_record, _ = _sealed_record(1, "N")
    assert peer_github_commit([turn_record]) is None


def test_turn_records_only_drops_moamteams_own_step0_record_shape():
    # Real record pasted live by moamteam after their audit came back
    # falsely TAMPERED: no "step" key at all, type "step0" (not
    # yanell11's "system_spec") -- confirms the fix is general, not
    # keyed to one peer's own chosen string.
    step0_record = {
        "commit": "2a02c4bd61e0f8fde0c6cc8d0040dd1117009aaa9ce3d8992a44c6fa4ba3e279",
        "nonce": "117fdb0eb54e44fffe234c9fc2fb0aec",
        "payload": {
            "code_version": "0.1.0", "git_commit": "f436fc345ab93f072a5cd85c17b29e3d846af6c5",
            "group_id": "moamteam", "type": "step0", "sub_game_number": 1,
        },
    }
    turn_record, _ = _sealed_record(1, "N")
    assert turn_records_only([step0_record, turn_record]) == [turn_record]


def test_verify_peer_records_real_moamteam_record_verifies_against_the_documented_formula():
    # Bit-for-bit real record from moamteam's own friendly g01, record
    # index 1 -- independently reproduces their stated commit before
    # this fix, confirming their formula (and this repo's own) agree.
    payload = {
        "hint": "Just slipped south past the back alleys.", "intent": "truth", "move": "MOVE:S",
        "move_detail": {"barrier_cell": None, "direction": "S", "kind": "step"},
        "position": [1, 0], "role": "police", "state": "grid=7x7;self=[1, 0];barriers=[]",
        "step": 1, "sub_game": 1,
    }
    record = {
        "commit": "d591aa2ce360978016edc33c3df473146397f4d70d7854af3d83076885369370",
        "nonce": "c5125963bf501699944e55864a5748e2",
        "payload": payload,
    }
    result = verify_peer_records([record], {1: record["commit"]})
    assert result == {"log_verified": True, "tampered": False, "mismatched_steps": []}


def test_peer_github_commit_reads_moamteams_own_git_commit_field_off_their_step0_shape():
    record = {
        "payload": {"type": "step0", "git_commit": "f436fc345ab93f072a5cd85c17b29e3d846af6c5"},
        "nonce": "n", "commit": "c",
    }
    assert peer_github_commit([record]) == "f436fc345ab93f072a5cd85c17b29e3d846af6c5"


def test_peer_github_commit_none_when_the_system_spec_record_declares_no_commit():
    record = {"payload": {"type": "system_spec", "step": 0}, "nonce": "n", "commit": "c"}
    assert peer_github_commit([record]) is None


def test_verify_peer_records_still_rejects_a_fabricated_turn_after_filtering():
    # turn_records_only must never weaken the existing anti-cheat guard
    # (test_verify_peer_records_rejects_a_record_for_a_step_we_never_saw_a_
    # commit_for) -- it only removes non-turn metadata, not unseen turns.
    fabricated, _real_commit = _sealed_record(5, "E")
    result = verify_peer_records(turn_records_only([fabricated]), {})
    assert result["tampered"] is True
    assert result["mismatched_steps"] == [5]


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
