"""Commit-Reveal cryptographic sealing (PRD_6 §2.1-2.4, §3; PLAN.md ADR-3):
the book's exact canonicalization formula -- the nonce is embedded *inside*
the hashed JSON object, never appended after it (the lecturer's sample
repo's rejected variant does the latter). There is no judge; trust between
two mutually-distrusting peers rests on this math, not good faith
(book Ch.5.1-5.2).
"""

import hashlib
import json
import secrets
from pathlib import Path

from thief_peer.constants import NONCE_BYTES


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def hash_config_file(path: str | Path) -> str:
    """Plain `sha256(raw file bytes)` -- rule 11 [FATAL]'s literal "byte-for-
    byte identical" requirement, not a semantic/field-value comparison.
    Canonical home for this (PRD_10 fix): both `domain/negotiation.py`'s
    native path and `interop/cop_wire.py`'s cop_v1 path need the exact same
    algorithm, so it lives here once rather than drifting into two copies.
    Matches the Cop repo's own `integrity/step0.py::hash_config_file`
    exactly (empirically verified, see `interop/cop_wire.py`)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CommitReveal:
    @staticmethod
    def seal(payload: dict) -> dict:
        nonce = secrets.token_hex(NONCE_BYTES)
        return {"nonce": nonce, "commit": CommitReveal.commit_of(payload, nonce)}

    @staticmethod
    def commit_of(payload: dict, nonce: str) -> str:
        full_payload = {**payload, "nonce": nonce}
        return hashlib.sha256(canonical_json(full_payload).encode("utf-8")).hexdigest()

    @staticmethod
    def verify(payload: dict, nonce: str, commit: str) -> bool:
        recomputed = CommitReveal.commit_of(payload, nonce)
        return secrets.compare_digest(recomputed, commit)


def audit_records(records: list[dict]) -> dict:
    """Re-verifies every {payload, commit} entry from a revealed opponent
    log (PRD_6 §2.3, §3) -- payload already carries its own nonce, per the
    AuditPayload wire shape (PLAN.md §5)."""
    failed_steps: list[int] = []
    for index, record in enumerate(records):
        full_payload = record["payload"]
        nonce = full_payload["nonce"]
        content = {key: value for key, value in full_payload.items() if key != "nonce"}
        if not CommitReveal.verify(content, nonce, record["commit"]):
            failed_steps.append(index)

    return {
        "passed": len(failed_steps) == 0,
        "verified_steps": len(records),
        "failed_steps": failed_steps,
    }
