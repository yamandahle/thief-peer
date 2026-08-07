"""report/artifact_helpers.py tests (PRD_7 §3, §5). canonical_sha256 reuses
domain/crypto.py's canonical_json (Stage 6, DRY) -- never a second
hashing/serialization implementation."""

import hashlib

from thief_peer.domain.crypto import canonical_json
from thief_peer.report.artifact_helpers import artifact_filenames, canonical_sha256


def test_canonical_sha256_matches_a_hand_computed_digest():
    payload = {"b": 2, "a": 1}
    expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    assert canonical_sha256(payload) == expected


def test_canonical_sha256_is_independent_of_dict_insertion_order():
    a = canonical_sha256({"grid_size": 7, "hint_word_limit": 15})
    b = canonical_sha256({"hint_word_limit": 15, "grid_size": 7})
    assert a == b


def test_artifact_filenames_match_the_book_appendix_naming_convention():
    names = artifact_filenames("group-a-vs-group-b", sub_game_number=3)

    assert names["declaration"] == "declaration_group-a-vs-group-b.json"
    assert names["config"] == "config_group-a-vs-group-b_g03.json"
    assert names["log"] == "log_group-a-vs-group-b_g03.json"
    assert names["result"] == "result_group-a-vs-group-b.json"


def test_artifact_filenames_declaration_and_result_are_per_match_not_per_sub_game():
    # Same game_id, different sub_game_number -> declaration/result filenames
    # must stay identical (once per match), only config/log vary.
    names1 = artifact_filenames("game-x", sub_game_number=1)
    names2 = artifact_filenames("game-x", sub_game_number=2)

    assert names1["declaration"] == names2["declaration"]
    assert names1["result"] == names2["result"]
    assert names1["config"] != names2["config"]
    assert names1["log"] != names2["log"]
