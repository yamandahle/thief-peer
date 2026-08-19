"""Per-turn Commit-Reveal sealing for the std_v1 protocol (spec Section 9).

Appendix D's turn message has no `move` field at all -- N/S/E/W/STAY is
never sent live. Read alongside Section 9 ("the commit is sent during
play; the nonce is withheld until the end-of-sub-game audit") and the
Cop repo's own established pattern for the identical situation ("State is
deliberately not part of this payload at all: the auditing side
reconstructs it locally by replaying the peer's own revealed Move
sequence"), the only coherent reading is that `move` is part of the
*hashed* payload -- committed to every turn, but only revealed later in
`submit_audit`'s records, exactly like this repo's own book-formula
already treats Move as hidden-until-reveal. This split (a `move` field
that is real payload but never appears in the live wire message) is this
implementation's own resolution of a real spec gap, not something the
spec states explicitly -- flagged as a real interop risk to verify
empirically (spec Section 15) against any third team's own implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from thief_peer.interop.std_v1.crypto import commit_of, fresh_nonce

# Sent live, in every receive_turn message.
_PUBLIC_FIELDS = (
    "step",
    "sender",
    "hint",
    "smell_grid",
    "barrier_placed",
    "capture_claim",
    "claim_response",
    "win_claim",
)
# Hashed into `commit` but withheld from the live message -- revealed only
# in the per-sub-game audit's `records`.
_HIDDEN_FIELDS = ("move",)


def build_turn_payload(
    step: int,
    sender: str,
    move: str,
    hint: str,
    smell_grid: dict[str, float],
    barrier_placed: list[int] | None = None,
    capture_claim: list[int] | None = None,
    claim_response: dict | None = None,
    win_claim: dict | None = None,
) -> dict:
    return {
        "step": step,
        "sender": sender,
        "move": move,
        "hint": hint,
        "smell_grid": smell_grid,
        "barrier_placed": barrier_placed,
        "capture_claim": capture_claim,
        "claim_response": claim_response,
        "win_claim": win_claim,
    }


def seal_turn(payload: dict) -> dict:
    """Returns {"nonce": ..., "commit": ...} -- the commit hashes the full
    payload (including the hidden `move`); the nonce is kept locally until
    the per-sub-game audit (rule 18's same secrecy-until-game-end
    principle every protocol in this repo already follows)."""
    nonce = fresh_nonce()
    commit = commit_of(payload, nonce)
    return {"nonce": nonce, "commit": commit}


def build_turn_message(payload: dict, commit: str) -> dict:
    """The actual `receive_turn` wire message: the public fields only
    (never `move`), plus the commit hash and a fresh timestamp -- matches
    Appendix D's own field list exactly."""
    public = {key: payload[key] for key in _PUBLIC_FIELDS}
    return {**public, "commit": commit, "timestamp": datetime.now(UTC).isoformat()}


def build_audit_record(payload: dict, nonce: str, commit: str) -> dict:
    """A revealed record for `submit_audit`'s own `records` list -- nested,
    not flat: `{"payload": {...full sealed fields, move now revealed...},
    "nonce": ..., "commit": ...}`. This is the kit-pinned disclosure shape
    (reconciled live against yanell11: their own reference auditor reads
    `record["payload"]`, not the record's own top-level keys) -- a flat
    `{**payload, "nonce": nonce}` record fails every audit against a peer
    expecting this nesting, symmetrically in both directions, and looks
    exactly like real tampering even though nothing was actually altered."""
    return {"payload": dict(payload), "nonce": nonce, "commit": commit}


def build_step0_record(sender: str, github_commit: str | None) -> dict:
    """A sealed declaration record disclosed alongside the real turn
    records in `submit_audit` -- real gap found live (yanell11, after we'd
    already built the reading side for her own equivalent record): this
    repo never sent one at all, so a peer's own audit had nothing to read
    `github_commit` off of, no matter how correct our negotiate-offer
    identity was. `payload.type` marks it as non-turn metadata (matches
    `audit.py::turn_records_only`'s own "any type key at all -> not a real
    turn" rule, so this repo's own peer never mistakes it for a fabricated
    turn record); `"system_spec"` specifically matches yanell11's own
    established convention, since this record exists for her benefit.
    `github_commit` is `None` when the caller has no commit to declare
    (e.g. the relay's own commit fetch failed) -- included as `None`
    rather than omitted, so a peer reading it sees an honest absence
    instead of inferring one from a missing key."""
    payload = {"type": "system_spec", "sender": sender, "github_commit": github_commit}
    sealed = seal_turn(payload)
    return build_audit_record(payload, sealed["nonce"], sealed["commit"])


def verify_record(record: dict, expected_commit: str) -> bool:
    """Re-hashes `record["payload"]` exactly as disclosed -- never
    reconstructed from this repo's own `_PUBLIC_FIELDS`/`_HIDDEN_FIELDS`
    names. A real cross-team peer is free to seal whatever payload shape
    its own kit uses (Section 9 hashes whatever the sender actually
    committed to, not a shared fixed schema); reconstructing from our own
    known field names silently built a *different* object than the one
    actually committed to, so every cross-team record failed this check
    regardless of real tampering -- confirmed empirically against
    yanell11's own real records (their commit reproduces bit-for-bit once
    hashed verbatim, not reconstructed). This is also strictly safer than
    the old reconstruction: a peer padding its payload with undeclared
    extra fields after sealing now breaks the hash immediately, instead of
    those extra fields being silently dropped before hashing and the
    tampering going undetected."""
    payload = record.get("payload")
    nonce = record.get("nonce")
    if payload is None or nonce is None:
        return False
    return commit_of(payload, nonce) == expected_commit
