"""CommitReveal tests (PRD_6 §2.1-2.4, §3, §5). There is no judge -- trust
rests on this math. The formula is a cross-repo interoperability contract:
get the canonicalization wrong and every audit spuriously fails regardless
of correctness (PRD_6 §2.2)."""

import ast
import hashlib
import inspect
import json

import pytest

from thief_peer.domain import crypto
from thief_peer.domain.crypto import CommitReveal, audit_records, canonical_json
from thief_peer.exceptions import CryptoError


def test_canonical_json_is_sorted_and_compact():
    payload = {"b": 2, "a": 1}
    assert canonical_json(payload) == '{"a":1,"b":2}'


def test_seal_then_verify_round_trips():
    payload = {"state": "s1", "move": "N", "intent": "truth"}
    sealed = CommitReveal.seal(payload)

    assert CommitReveal.verify(payload, sealed["nonce"], sealed["commit"]) is True


@pytest.mark.parametrize("field", ["state", "move", "intent"])
def test_verify_fails_if_any_field_changes_after_sealing(field):
    payload = {"state": "s1", "move": "N", "intent": "truth"}
    sealed = CommitReveal.seal(payload)

    tampered = dict(payload)
    tampered[field] = tampered[field] + "-tampered"

    assert CommitReveal.verify(tampered, sealed["nonce"], sealed["commit"]) is False


def test_verify_fails_if_the_nonce_changes():
    payload = {"state": "s1", "move": "N", "intent": "truth"}
    sealed = CommitReveal.seal(payload)

    assert CommitReveal.verify(payload, sealed["nonce"] + "0", sealed["commit"]) is False


def test_commit_of_matches_a_hand_computed_digest_for_a_fixed_tuple():
    # Pins the exact book formula byte-for-byte: nonce embedded INSIDE the
    # canonical JSON object, not appended after it (PLAN.md ADR-3 -- the
    # lecturer's sample repo's rejected variant does the latter).
    payload = {"state": "S", "move": "N", "intent": "truth"}
    nonce = "deadbeef"

    expected_payload_str = json.dumps(
        {"state": "S", "move": "N", "intent": "truth", "nonce": "deadbeef"},
        sort_keys=True,
        separators=(",", ":"),
    )
    expected = hashlib.sha256(expected_payload_str.encode("utf-8")).hexdigest()

    assert CommitReveal.commit_of(payload, nonce) == expected


def test_commit_of_does_not_use_the_pipe_appended_variant():
    # The rejected lecturer-repo variant: SHA256(canonical_json(payload) +
    # "|" + nonce). Confirms our formula is genuinely different, not just
    # "produces a hash that happens to differ by coincidence."
    payload = {"state": "S", "move": "N", "intent": "truth"}
    nonce = "deadbeef"

    rejected_variant = hashlib.sha256(
        (canonical_json(payload) + "|" + nonce).encode("utf-8")
    ).hexdigest()

    assert CommitReveal.commit_of(payload, nonce) != rejected_variant


def test_seal_generates_a_fresh_nonce_each_time():
    payload = {"state": "s1", "move": "N", "intent": "truth"}
    first = CommitReveal.seal(payload)
    second = CommitReveal.seal(payload)

    assert first["nonce"] != second["nonce"]
    assert first["commit"] != second["commit"]


def test_nonce_source_is_secrets_never_random():
    # Static check, not just a behavioral one: `random` must never be
    # imported in this module at all (PRD_6 §5).
    source = inspect.getsource(crypto)
    tree = ast.parse(source)
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)

    assert "random" not in imported_names
    assert "secrets" in imported_names
    assert "secrets.token_hex" in source
    assert "secrets.compare_digest" in source


def test_audit_records_passes_on_a_clean_log():
    records = []
    for i in range(3):
        payload = {"state": f"s{i}", "move": "N", "intent": "truth"}
        sealed = CommitReveal.seal(payload)
        records.append({"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]})

    result = audit_records(records)

    assert result == {"passed": True, "verified_steps": 3, "failed_steps": []}


def test_audit_records_catches_a_tampered_field_and_reports_the_rest_clean():
    records = []
    for i in range(3):
        payload = {"state": f"s{i}", "move": "N", "intent": "truth"}
        sealed = CommitReveal.seal(payload)
        records.append({"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]})

    # Corrupt step 1's move after sealing -- exactly what a cheater trying
    # to retroactively switch a decision would do.
    records[1]["payload"]["move"] = "S"

    result = audit_records(records)

    assert result["passed"] is False
    assert result["failed_steps"] == [1]
    assert result["verified_steps"] == 3


def test_audit_records_on_an_empty_log_passes_trivially():
    assert audit_records([]) == {"passed": True, "verified_steps": 0, "failed_steps": []}


def test_verify_uses_constant_time_comparison_not_bare_equality():
    source = inspect.getsource(crypto.CommitReveal.verify)
    assert "secrets.compare_digest" in source
    assert "==" not in source.replace("__eq__", "")


def test_crypto_error_exists_for_future_seal_verify_failure_paths():
    # Reserved per exceptions.py's own docstring ("Stage 6") -- not yet
    # raised anywhere in this stage's happy-path API, but must exist and be
    # a distinct, catchable type when a later caller needs it.
    assert issubclass(CryptoError, Exception)
