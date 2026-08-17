"""interop/std_v1/terms.py tests: the 14-key term set is a closed set
(spec Appendix A) -- both a missing and an extra key must fail loudly,
since a silently-different local terms shape would produce a different
canonical signature than a spec-compliant peer's own terms."""

import json

import pytest

from thief_peer.exceptions import SimulationError
from thief_peer.interop.std_v1.terms import TERM_KEYS, load_terms, validate_terms

_VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "min_center_intensity": 0.5,
    "max_steps": 35,
    "barriers_max": 14,
    "setting": "Haifa",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
    "num_games": 6,
}


def test_term_keys_has_exactly_fourteen_entries():
    assert len(TERM_KEYS) == 14


def test_validate_terms_accepts_the_full_valid_set():
    validate_terms(_VALID_TERMS)  # must not raise


def test_validate_terms_rejects_a_non_dict():
    with pytest.raises(SimulationError):
        validate_terms(["not", "a", "dict"])


def test_validate_terms_rejects_a_missing_key():
    incomplete = dict(_VALID_TERMS)
    del incomplete["num_games"]
    with pytest.raises(SimulationError, match="missing required key"):
        validate_terms(incomplete)


def test_validate_terms_rejects_an_extra_key():
    extra = dict(_VALID_TERMS)
    extra["unexpected_field"] = 1
    with pytest.raises(SimulationError, match="unexpected key"):
        validate_terms(extra)


def test_load_terms_reads_and_validates_the_checked_in_file(tmp_path):
    path = tmp_path / "terms.json"
    path.write_text(json.dumps(_VALID_TERMS), encoding="utf-8")
    assert load_terms(path) == _VALID_TERMS


def test_load_terms_default_path_is_the_real_checked_in_config_file():
    terms = load_terms()  # uses DEFAULT_TERMS_PATH relative to cwd (repo root)
    assert set(terms) == set(TERM_KEYS)
