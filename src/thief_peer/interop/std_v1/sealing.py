"""Per-turn Commit-Reveal sealing for the std_v1 protocol (spec Section 9).

Appendix D's turn message has no `move` field at all -- N/S/E/W/STAY is
never sent live. Read alongside Section 9 ("the commit is sent during
play; the nonce is withheld until the end-of-sub-game audit") and
yamanagh-cop's own established pattern for the identical situation
("State is deliberately not part of this payload at all: the auditing
side reconstructs it locally by replaying the peer's own revealed Move
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
_PAYLOAD_FIELDS = _PUBLIC_FIELDS + _HIDDEN_FIELDS


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


def build_audit_record(payload: dict, nonce: str) -> dict:
    """A revealed record for `submit_audit`'s own `records` list -- the
    full payload (including `move`, now finally revealed) plus its nonce,
    letting the receiver recompute `commit_of` and compare against what
    was actually sent as `commit` during play, and replay the real move
    sequence (Section 9's own "re-hashes every record... checks that each
    revealed commit matches what was played")."""
    return {**payload, "nonce": nonce}


def verify_record(record: dict, expected_commit: str) -> bool:
    nonce = record.get("nonce")
    if nonce is None:
        return False
    payload = {key: record.get(key) for key in _PAYLOAD_FIELDS}
    return commit_of(payload, nonce) == expected_commit
