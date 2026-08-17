"""Cryptographic derivations, reproduced exactly from the spec's own
Appendix B pseudocode. A dedicated implementation, not a reuse of
domain/crypto.py's own CommitReveal -- the two schemes differ in real,
breaking ways: this spec's commit_of concatenates canonical(payload) +
"|" + nonce as a plain string (the nonce never enters the hashed JSON at
all), while this repo's own book-formula embeds the nonce inside the
hashed object instead. Reusing either implementation for the other's job
would silently produce the wrong bytes -- two different peers computing
different hashes over what looks like "the same" data is exactly the
failure mode a shared spec exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid

NONCE_HEX_CHARS = 32  # secrets.token_hex(16) -> 32 lowercase hex chars


def canonical(obj) -> str:
    """The spec's one canonical form, used for every hash and signature.
    `ensure_ascii=False` is required explicitly by the spec -- unlike
    domain/crypto.py::canonical_json, which never needed it (every payload
    there was already pure ASCII), a value here (e.g. a non-ASCII hint or
    member name) would canonicalize to different bytes on each side
    without it."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fresh_nonce() -> str:
    return secrets.token_hex(16)


def commit_of(payload: dict, nonce: str) -> str:
    """SHA-256 over canonical(payload) + a literal pipe byte (0x7C) + the
    raw nonce string -- never over a JSON object containing the nonce."""
    material = canonical(payload) + "|" + nonce
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def derive_game_id(group_a: str, group_b: str) -> str:
    """Order-independent: both peers compute the identical id regardless
    of which side is "local" -- the two group ids sorted, joined by the
    literal string "-vs-"."""
    return "-vs-".join(sorted([group_a, group_b]))


def derive_game_uid(terms: dict, group_a: str, group_b: str) -> str:
    """A UUID built from the first 16 raw bytes (not hex) of a SHA-256 over
    canonical(terms) + "|" + the two sorted group ids joined by "|" --
    order-independent for the same reason derive_game_id is."""
    pair = sorted([group_a, group_b])
    seed = canonical(terms) + "|" + "|".join(pair)
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16]))


def consensus_digest(consensus_obj: dict) -> str:
    """SHA-256 hex digest over the canonical Section-11 consensus object --
    the one value both peers must agree on bit-for-bit at series end."""
    return hashlib.sha256(canonical(consensus_obj).encode("utf-8")).hexdigest()
