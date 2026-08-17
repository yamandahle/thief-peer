"""scent_model_lock.py: the optional, additive Locked-Model Declaration
used to interoperate with the Imreec league kit's own scent-model
refusal rule (docs/IMREEC_LEAGUE_KIT_COMPAT.md). Never required by the
Guide itself -- these tests only pin its own internal correctness."""

from thief_peer.interop.std_v1.crypto import canonical
from thief_peer.interop.std_v1.scent_model_lock import build_scent_model_lock

_TERMS = {"emit_intensity": 0.9, "decay_per_step": 0.1}


def test_declares_the_book_model_by_name():
    lock = build_scent_model_lock(_TERMS)
    assert lock["family"] == "scent_model"
    assert lock["name"] == "multiplicative_book_v1"


def test_worked_example_matches_appendix_e_09_to_081():
    lock = build_scent_model_lock(_TERMS)
    assert lock["example"] == {"tau_before": 0.9, "tau_after": 0.81}


def test_params_are_sourced_from_the_real_signed_terms_not_hardcoded():
    lock = build_scent_model_lock({"emit_intensity": 0.45, "decay_per_step": 0.2})
    assert lock["params"]["emit_intensity"] == 0.45
    assert lock["params"]["decay_per_step"] == 0.2
    assert lock["params"]["cap"] == 0.45


def test_sha256_is_the_canonical_hash_of_the_declaration_body():
    import hashlib

    lock = build_scent_model_lock(_TERMS)
    body = {k: v for k, v in lock.items() if k != "sha256"}
    assert lock["sha256"] == hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def test_two_calls_with_identical_terms_produce_identical_hashes():
    assert build_scent_model_lock(_TERMS)["sha256"] == build_scent_model_lock(dict(_TERMS))["sha256"]


def test_matches_the_cop_repos_own_declaration_bit_for_bit():
    """The two repos were built to mirror each other's std_v1 package --
    given the real, checked-in interop_spec_terms.json values, both sides
    must produce the identical declaration (and therefore the identical
    sha256), not just individually well-formed output."""
    from thief_peer.interop.std_v1.terms import load_terms

    real_terms = load_terms()
    lock = build_scent_model_lock(real_terms)
    assert lock["sha256"] == "638de8481c99902fcd0a5f6cded6ee1355a35a14353e6c255f904ec6ef88b5a6"
