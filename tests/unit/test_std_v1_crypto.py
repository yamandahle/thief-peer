"""interop/std_v1/crypto.py tests -- reproduces the spec's own Appendix B
pseudocode exactly; a deviation here breaks interoperability with any
other team's implementation, not just our own code."""

import json
import uuid

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
    # ensure_ascii=False, required by the spec explicitly -- an escaped
    # \uXXXX form would canonicalize differently than the raw character.
    assert canonical({"name": "Haifa חיפה"}) == json.dumps(
        {"name": "Haifa חיפה"}, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert "\\u" not in canonical({"name": "חיפה"})


def test_fresh_nonce_is_32_lowercase_hex_chars():
    nonce = fresh_nonce()
    assert len(nonce) == 32
    assert all(c in "0123456789abcdef" for c in nonce)


def test_fresh_nonce_is_different_each_call():
    assert fresh_nonce() != fresh_nonce()


def test_commit_of_matches_manual_derivation():
    payload = {"b": 1, "a": 2}
    nonce = "0" * 32
    expected = __import__("hashlib").sha256((canonical(payload) + "|" + nonce).encode("utf-8")).hexdigest()
    assert commit_of(payload, nonce) == expected


def test_commit_of_treats_an_explicit_nonce_key_as_ordinary_payload_data():
    # The defining difference from domain/crypto.py's own CommitReveal:
    # this spec's commit_of never embeds `nonce` into the hashed JSON --
    # it's concatenated afterward as a plain string. So a payload that
    # happens to carry its own "nonce" field is just ordinary data; giving
    # it a different value changes the hash like any other field would.
    nonce = "abc123"
    payload_a = {"a": 1, "nonce": "x"}
    payload_b = {"a": 1, "nonce": "y"}
    assert commit_of(payload_a, nonce) != commit_of(payload_b, nonce)


def test_commit_of_is_sensitive_to_the_nonce():
    payload = {"a": 1}
    assert commit_of(payload, "nonce-one") != commit_of(payload, "nonce-two")


def test_commit_of_is_sensitive_to_the_payload():
    nonce = "abc123"
    assert commit_of({"a": 1}, nonce) != commit_of({"a": 2}, nonce)


def test_derive_game_id_sorts_and_joins_with_vs():
    assert derive_game_id("teamB", "teamA") == "teamA-vs-teamB"
    assert derive_game_id("teamA", "teamB") == "teamA-vs-teamB"


def test_derive_game_uid_is_order_independent_and_a_real_uuid():
    terms = {"board_size": 7}
    uid_a = derive_game_uid(terms, "teamA", "teamB")
    uid_b = derive_game_uid(terms, "teamB", "teamA")
    assert uid_a == uid_b
    assert uuid.UUID(uid_a)  # does not raise


def test_derive_game_uid_changes_when_terms_change():
    uid_a = derive_game_uid({"board_size": 7}, "teamA", "teamB")
    uid_b = derive_game_uid({"board_size": 8}, "teamA", "teamB")
    assert uid_a != uid_b


def test_derive_game_uid_uses_raw_digest_bytes_not_hex():
    import hashlib

    terms = {"board_size": 7}
    pair = sorted(["teamA", "teamB"])
    seed = canonical(terms) + "|" + "|".join(pair)
    expected = str(uuid.UUID(bytes=hashlib.sha256(seed.encode("utf-8")).digest()[:16]))
    assert derive_game_uid(terms, "teamA", "teamB") == expected


def test_consensus_digest_is_64_lowercase_hex():
    digest = consensus_digest({"game_id": "a-vs-b", "game_uid": "x", "sub_games": []})
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_consensus_digest_is_deterministic():
    obj = {"game_id": "a-vs-b", "game_uid": "x", "sub_games": [{"sub_game_number": 1}]}
    assert consensus_digest(obj) == consensus_digest(obj)
