"""report/artifacts.py tests (PRD_7 §2.6, §3, §4). Pure packaging functions
only -- every field comes from data already computed in Stages 1-6, nothing
new is computed here (the risk this design avoids by construction is a
report silently recomputing a value differently than how it was sealed)."""

from thief_peer.report.artifact_helpers import canonical_sha256
from thief_peer.report.artifact_schemas import SCHEMA_VERSION
from thief_peer.report.artifacts import build_config, build_declaration, build_log, build_result


def test_build_declaration_has_the_documented_fields():
    declaration = build_declaration(
        game_id="a-vs-b",
        game_uid="a-vs-b_g01",
        num_sub_games=1,
        groups={"group_1": {"identity": "thief"}, "group_2": {"identity": "cop"}},
    )

    assert declaration["schema_version"] == SCHEMA_VERSION
    assert declaration["game_id"] == "a-vs-b"
    assert declaration["game_uid"] == "a-vs-b_g01"
    assert declaration["num_sub_games"] == 1
    assert declaration["groups"]["group_1"]["identity"] == "thief"
    assert "timestamp" in declaration


def test_build_declaration_timestamp_is_injectable_for_deterministic_tests():
    declaration = build_declaration(
        game_id="a", game_uid="a_g01", num_sub_games=1, groups={}, timestamp="2026-01-01T00:00:00Z"
    )
    assert declaration["timestamp"] == "2026-01-01T00:00:00Z"


def test_build_config_includes_a_sha256_matching_the_shared_helper():
    terms = {"grid_size": 7, "hint_word_limit": 15}
    config = build_config(shared_terms=terms, config_name="config_dev_g01")

    assert config["config_name"] == "config_dev_g01"
    assert config["terms"] == terms
    assert config["config_sha256"] == canonical_sha256(terms)


def test_build_config_sha256_changes_if_a_single_term_changes():
    a = build_config(shared_terms={"grid_size": 7}, config_name="c")
    b = build_config(shared_terms={"grid_size": 9}, config_name="c")
    assert a["config_sha256"] != b["config_sha256"]


def test_build_log_wraps_records_and_audit_verbatim():
    records = [{"payload": {"state": "s"}, "commit": "abc"}]
    audit = {"passed": True, "verified_steps": 1, "failed_steps": []}

    log = build_log(records=records, audit=audit)

    assert log["records"] == records
    assert log["audit"] == audit


def test_build_result_carries_final_result_and_optional_signature():
    final_result = {"winner_group": "thief", "tokens_total_series": 1234}
    result = build_result(final_result=final_result, mutual_agreement_signature="sig-abc")

    assert result["final_result"] == final_result
    assert result["mutual_agreement_signature"] == "sig-abc"


def test_build_result_signature_defaults_to_none():
    result = build_result(final_result={"winner_group": "thief"})
    assert result["mutual_agreement_signature"] is None
