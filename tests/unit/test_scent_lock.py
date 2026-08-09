"""domain/scent_lock.py tests (ch.4.5 ceremony, rule 23 FATAL). The default
values (0.9 / 0.10 / 5) produce a hash independently verified byte-for-byte
against the Cop repo's own `integrity/scent_model_lock.py` (this project's
"verify empirically" discipline, not just a self-consistency check) --
`5aac6e62703e2afffac1ad4738fa3f8e2c85da964dbf7a2de17fd3e00d516386`, pinned
below so a future change to either implementation's shape is caught."""

from thief_peer.domain.scent_lock import scent_lock_hash, scent_lock_payload

_DEFAULT_CENTER_INTENSITY = 0.9
_DEFAULT_DECAY_RATE = 0.10
_DEFAULT_FIELD_SIZE = 5
_KNOWN_GOOD_HASH = "5aac6e62703e2afffac1ad4738fa3f8e2c85da964dbf7a2de17fd3e00d516386"


def test_default_params_match_the_cop_repos_independently_computed_hash():
    assert (
        scent_lock_hash(_DEFAULT_CENTER_INTENSITY, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
        == _KNOWN_GOOD_HASH
    )


def test_worked_example_matches_the_books_own_09_to_081_illustration():
    payload = scent_lock_payload(_DEFAULT_CENTER_INTENSITY, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
    example = payload["worked_numeric_example"]
    assert example["center_after_emission"] == "0.9000000000"
    assert example["center_after_one_decay_round"] == "0.8100000000"


def test_hash_is_deterministic_across_repeated_calls():
    first = scent_lock_hash(_DEFAULT_CENTER_INTENSITY, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
    second = scent_lock_hash(_DEFAULT_CENTER_INTENSITY, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
    assert first == second


def test_a_different_decay_rate_produces_a_different_hash():
    default = scent_lock_hash(_DEFAULT_CENTER_INTENSITY, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
    drifted = scent_lock_hash(_DEFAULT_CENTER_INTENSITY, 0.20, _DEFAULT_FIELD_SIZE)
    assert default != drifted


def test_a_different_center_intensity_produces_a_different_hash():
    default = scent_lock_hash(_DEFAULT_CENTER_INTENSITY, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
    drifted = scent_lock_hash(0.7, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
    assert default != drifted


def test_payload_carries_the_fixed_formula_description_verbatim():
    payload = scent_lock_payload(_DEFAULT_CENTER_INTENSITY, _DEFAULT_DECAY_RATE, _DEFAULT_FIELD_SIZE)
    assert "tau(t+1) = max(0, (1-rho)*tau(t) + delta_tau)" in payload["formula_description"]
