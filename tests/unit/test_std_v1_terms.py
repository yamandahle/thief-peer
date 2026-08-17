"""interop/std_v1/terms.py tests."""

import json

import pytest

from thief_peer.exceptions import SimulationError
from thief_peer.interop.std_v1.terms import TERM_KEYS, load_terms, validate_terms


def test_load_terms_loads_the_real_checked_in_file():
    terms = load_terms()
    assert set(terms) == set(TERM_KEYS)
    assert terms["board_size"] == 7
    assert terms["setting"] == "Haifa"
    assert terms["thief_start"] == [3, 3]
    assert terms["cop_start"] == [0, 0]
    assert terms["min_center_intensity"] == 0.5


def test_load_terms_from_a_custom_path(tmp_path):
    path = tmp_path / "terms.json"
    path.write_text(json.dumps(dict.fromkeys(TERM_KEYS, 1)), encoding="utf-8")
    terms = load_terms(path)
    assert set(terms) == set(TERM_KEYS)


def test_validate_terms_rejects_a_non_dict():
    with pytest.raises(SimulationError, match="object"):
        validate_terms(["not", "a", "dict"])


def test_validate_terms_rejects_a_missing_key():
    incomplete = {k: 1 for k in TERM_KEYS if k != "setting"}
    with pytest.raises(SimulationError, match="missing"):
        validate_terms(incomplete)


def test_validate_terms_rejects_an_extra_key():
    extra = dict.fromkeys(TERM_KEYS, 1)
    extra["unexpected_field"] = "value"
    with pytest.raises(SimulationError, match="unexpected"):
        validate_terms(extra)


def test_validate_terms_accepts_a_complete_closed_set():
    validate_terms(dict.fromkeys(TERM_KEYS, 1))  # must not raise
