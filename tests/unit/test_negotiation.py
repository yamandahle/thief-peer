"""domain/negotiation.py tests (PRD_6 §3, §5; PLAN.md ADR-6). canonical_terms
projects our locally-named config into a fixed, documented wire vocabulary
-- interoperability with an independently-built Cop repo doesn't depend on
them using our internal game.json key names, only on both sides producing
the same *values* for this documented set of wire-level keys."""

import pytest

from thief_peer.domain.crypto import CommitReveal
from thief_peer.domain.negotiation import (
    CANONICAL_TERM_KEYS,
    MINIMUM_FLOORS,
    Negotiation,
    canonical_terms,
)
from thief_peer.exceptions import ConfigError
from thief_peer.shared.config import ConfigManager

_GAME_JSON = """
{
  "board_and_agents": {"grid_size": 7, "num_agents": 2, "axis_origin_corner": "top-left",
                        "axis_start_index": 0, "thief_start": [3, 3], "cop_start": [0, 0]},
  "world": {"map_area": "New York", "hint_max_words": 15},
  "movement_and_barriers": {"move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
                             "max_moves": 35, "survival_threshold": 35},
  "scoring": {"capture_cop": 20, "capture_thief": 5, "survival_cop": 5, "survival_thief": 10,
              "tie_score": 2, "technical_loss": 0},
  "pheromones": {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5}
}
"""


def _config(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text("[network]\nmy_port = 8802\n", encoding="utf-8")
    json_path = tmp_path / "game.json"
    json_path.write_text(_GAME_JSON, encoding="utf-8")
    return ConfigManager(toml_path, json_path)


def test_canonical_terms_covers_every_documented_wire_key(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    assert set(terms) == set(CANONICAL_TERM_KEYS)


def test_canonical_terms_reads_the_real_values(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    assert terms["grid_size"] == 7
    assert terms["scent_decay_rate"] == 0.10
    assert terms["hint_word_limit"] == 15


def test_canonical_terms_fails_fast_if_a_required_term_is_missing(tmp_path):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text("[network]\nmy_port = 8802\n", encoding="utf-8")
    json_path = tmp_path / "game.json"
    json_path.write_text('{"board_and_agents": {"grid_size": 7}}', encoding="utf-8")
    config = ConfigManager(toml_path, json_path)

    with pytest.raises(ConfigError):
        canonical_terms(config)


def test_signed_produces_a_verifiable_commit(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)

    assert CommitReveal.verify(terms, signed["nonce"], signed["commit"]) is True


def test_verify_peer_accepts_matching_terms(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)

    Negotiation.verify_peer(
        signed["terms"], signed["nonce"], signed["commit"], terms, signed["scent_lock_hash"]
    )


def test_verify_peer_rejects_a_tampered_commit(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)
    tampered_terms = {**signed["terms"], "grid_size": 99}

    with pytest.raises(ConfigError, match="tamper"):
        Negotiation.verify_peer(
            tampered_terms, signed["nonce"], signed["commit"], terms, signed["scent_lock_hash"]
        )


def test_verify_peer_rejects_a_single_mismatched_field_and_names_it(tmp_path):
    my_terms = canonical_terms(_config(tmp_path))
    their_terms = dict(my_terms)
    their_terms["grid_size"] = 9  # single differing value
    signed = Negotiation.signed(their_terms)

    with pytest.raises(ConfigError, match="grid_size"):
        Negotiation.verify_peer(
            signed["terms"], signed["nonce"], signed["commit"], my_terms, signed["scent_lock_hash"]
        )


def test_verify_peer_accepts_even_if_local_key_names_would_have_differed(tmp_path):
    # The whole point of canonicalization: two independently-named local
    # schemas produce the SAME wire vocabulary, so this call has no idea
    # (and doesn't need to) what either side privately calls these fields.
    terms = canonical_terms(_config(tmp_path))
    assert "board_and_agents.grid_size" not in terms  # wire key, not our local dotted path
    assert "grid_size" in terms


def test_signed_includes_a_scent_lock_hash(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)

    assert len(signed["scent_lock_hash"]) == 64  # sha256 hexdigest


def test_verify_peer_rejects_a_scent_lock_hash_mismatch_even_with_matching_terms(tmp_path):
    # ch.4.5/rule 23: identical negotiated *numbers* don't guarantee
    # identical *formula behavior* -- a peer whose ScentField implementation
    # has silently drifted must still be caught here.
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)

    with pytest.raises(ConfigError, match="scent-lock"):
        Negotiation.verify_peer(
            signed["terms"], signed["nonce"], signed["commit"], terms, "0" * 64
        )


def test_signed_includes_the_given_config_sha256(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms, config_sha256="deadbeef")
    assert signed["config_sha256"] == "deadbeef"


def test_signed_config_sha256_defaults_to_none(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)
    assert signed["config_sha256"] is None


def test_verify_peer_accepts_matching_config_sha256(tmp_path):
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)

    Negotiation.verify_peer(
        signed["terms"],
        signed["nonce"],
        signed["commit"],
        terms,
        signed["scent_lock_hash"],
        my_config_sha256="same-hash",
        their_config_sha256="same-hash",
    )


def test_verify_peer_rejects_a_config_sha256_mismatch_even_with_matching_terms(tmp_path):
    # rule 11 [FATAL]: two config files that differ only in formatting/
    # whitespace carry identical negotiated *values* and would still pass
    # the term-by-term check above -- this catches that class of drift.
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)

    with pytest.raises(ConfigError, match="byte-identical"):
        Negotiation.verify_peer(
            signed["terms"],
            signed["nonce"],
            signed["commit"],
            terms,
            signed["scent_lock_hash"],
            my_config_sha256="my-hash",
            their_config_sha256="a-different-hash",
        )


def test_verify_peer_rejects_two_teams_mutually_agreeing_to_lower_a_minimum(tmp_path):
    # Rule 12 [FATAL]: the term-by-term symmetry check alone can't catch
    # this -- both sides genuinely match each other, they just agreed on
    # an illegal value *together*. grid_size's real floor is 7.
    my_terms = canonical_terms(_config(tmp_path))
    my_terms["grid_size"] = 5  # both "teams" agree on this, identically
    signed = Negotiation.signed(my_terms)

    with pytest.raises(ConfigError, match="minimum floor"):
        Negotiation.verify_peer(
            signed["terms"], signed["nonce"], signed["commit"], my_terms, signed["scent_lock_hash"]
        )


@pytest.mark.parametrize("key", sorted(MINIMUM_FLOORS))
def test_verify_peer_rejects_each_minimum_status_field_one_below_its_floor(tmp_path, key):
    my_terms = canonical_terms(_config(tmp_path))
    my_terms[key] = MINIMUM_FLOORS[key] - 1
    signed = Negotiation.signed(my_terms)

    with pytest.raises(ConfigError, match=key):
        Negotiation.verify_peer(
            signed["terms"], signed["nonce"], signed["commit"], my_terms, signed["scent_lock_hash"]
        )


def test_verify_peer_accepts_a_minimum_status_value_raised_above_the_floor(tmp_path):
    # Rule 12 permits raising a minimum, only forbids lowering it.
    my_terms = canonical_terms(_config(tmp_path))
    my_terms["max_barriers"] = 20  # raised above the 14 floor, by agreement
    signed = Negotiation.signed(my_terms)

    Negotiation.verify_peer(
        signed["terms"], signed["nonce"], signed["commit"], my_terms, signed["scent_lock_hash"]
    )


def test_verify_peer_accepts_exactly_at_the_floor_not_just_above_it(tmp_path):
    my_terms = canonical_terms(_config(tmp_path))
    my_terms["survival_threshold"] = MINIMUM_FLOORS["survival_threshold"]  # exactly at the floor
    signed = Negotiation.signed(my_terms)

    Negotiation.verify_peer(
        signed["terms"], signed["nonce"], signed["commit"], my_terms, signed["scent_lock_hash"]
    )


def test_verify_peer_skips_the_config_sha256_check_when_either_side_has_none(tmp_path):
    # An isolated caller with no file path handy (e.g. this test's own
    # in-memory config) must not be forced to fabricate a hash -- the
    # term-by-term check is the unconditional floor either way.
    terms = canonical_terms(_config(tmp_path))
    signed = Negotiation.signed(terms)

    Negotiation.verify_peer(
        signed["terms"],
        signed["nonce"],
        signed["commit"],
        terms,
        signed["scent_lock_hash"],
        my_config_sha256=None,
        their_config_sha256="theirs-only",
    )
