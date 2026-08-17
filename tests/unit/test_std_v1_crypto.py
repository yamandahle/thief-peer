"""interop/std_v1/crypto.py tests: this spec's own commit_of formula
(canonical(payload) + "|" + nonce, nonce never inside the hashed JSON)
is a deliberately different scheme from this repo's own book-formula
commit-reveal -- these tests pin the exact bytes so a future refactor
can't accidentally drift the two schemes back together."""

import json

from thief_peer.interop.std_v1.crypto import (
    canonical,
    commit_of,
    consensus_digest,
    derive_game_id,
    derive_game_uid,
    fresh_nonce,
)


def test_canonical_sorts_keys_and_uses_compact_separators():
    assert canonical({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_does_not_escape_non_ascii():
    assert canonical({"hint": "café"}) == '{"hint":"café"}'


def test_fresh_nonce_is_32_lowercase_hex_chars():
    nonce = fresh_nonce()
    assert len(nonce) == 32
    assert all(c in "0123456789abcdef" for c in nonce)


def test_commit_of_hashes_canonical_payload_pipe_nonce_not_a_json_object():
    import hashlib

    payload = {"step": 1, "move": "N"}
    nonce = "deadbeef"
    expected = hashlib.sha256((canonical(payload) + "|" + nonce).encode("utf-8")).hexdigest()
    assert commit_of(payload, nonce) == expected


def test_commit_of_changes_if_nonce_changes_but_payload_does_not():
    payload = {"step": 1}
    assert commit_of(payload, "nonce-a") != commit_of(payload, "nonce-b")


def test_derive_game_id_is_order_independent():
    assert derive_game_id("Alpha", "Beta") == derive_game_id("Beta", "Alpha")
    assert derive_game_id("Alpha", "Beta") == "Alpha-vs-Beta"


def test_derive_game_uid_is_order_independent_and_a_valid_uuid():
    import uuid

    terms = {"board_size": 7}
    uid_ab = derive_game_uid(terms, "Alpha", "Beta")
    uid_ba = derive_game_uid(terms, "Beta", "Alpha")
    assert uid_ab == uid_ba
    assert uuid.UUID(uid_ab)  # does not raise


def test_derive_game_uid_changes_if_terms_change():
    assert derive_game_uid({"a": 1}, "A", "B") != derive_game_uid({"a": 2}, "A", "B")


def test_consensus_digest_is_a_sha256_hex_digest_of_canonical_form():
    import hashlib

    obj = {"game_id": "A-vs-B", "game_uid": "x", "sub_games": []}
    expected = hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert consensus_digest(obj) == expected
