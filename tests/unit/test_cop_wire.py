"""interop/cop_wire.py tests. The two pinned hashes below were verified
empirically against the Cop repo's own cloned source
(`integrity/step0.py::sign_step0`, `integrity/scent_model_lock.py::
compute_scent_model_hash`) producing byte-identical output for the same
inputs -- not just self-consistency, real cross-repo agreement."""

from thief_peer.interop.cop_wire import (
    build_cop_declaration,
    build_cop_hardware,
    deserialize_scent_from_cop,
    serialize_scent_for_cop,
    sign_cop_declaration,
)

_KNOWN_GOOD_SIGNATURE = "432f16e658a3c12d1324012ab1799180c32ff03e6a28e7608883ed3540ae944c"


def _declaration():
    return build_cop_declaration(
        hardware={
            "os_name": "Windows",
            "cpu_cores": 8,
            "ram_gb": 16.0,
            "gpu_present": False,
            "gpu_vram_gb": None,
            "llm_model": "template",
        },
        code_commit_hash="abc123",
        group_name="thief-team",
        sub_game_number=1,
        config_sha256="deadbeef",
        scent_model_sha256="cafebabe",
    )


def test_sign_cop_declaration_matches_the_cop_repos_independently_computed_signature():
    assert sign_cop_declaration(_declaration()) == _KNOWN_GOOD_SIGNATURE


def test_sign_cop_declaration_is_deterministic():
    declaration = _declaration()
    assert sign_cop_declaration(declaration) == sign_cop_declaration(declaration)


def test_sign_cop_declaration_changes_if_any_field_changes():
    tampered = {**_declaration(), "group_name": "different-team"}
    assert sign_cop_declaration(tampered) != _KNOWN_GOOD_SIGNATURE


def test_build_cop_hardware_maps_sysinfo_spec_onto_her_field_names():
    spec = {"os": "Linux 6.1", "cpu_cores": 4, "ram_gb": 8.0, "gpu": "RTX 3080", "vram_gb": 10.0}
    hardware = build_cop_hardware(spec, llm_model="claude-sonnet-5")

    assert hardware == {
        "os_name": "Linux 6.1",
        "cpu_cores": 4,
        "ram_gb": 8.0,
        "gpu_present": True,
        "gpu_vram_gb": 10.0,
        "llm_model": "claude-sonnet-5",
    }


def test_build_cop_hardware_falls_back_honestly_when_detection_failed():
    spec = {"os": None, "cpu_cores": None, "ram_gb": None, "gpu": None, "vram_gb": None}
    hardware = build_cop_hardware(spec, llm_model="")

    assert hardware["os_name"] == "unknown"
    assert hardware["cpu_cores"] == 1
    assert hardware["ram_gb"] == 0.01
    assert hardware["gpu_present"] is False
    assert hardware["llm_model"] == "none"


def test_serialize_scent_for_cop_matches_her_col_row_value_shape():
    # our snapshot key is "row,col"; her wire shape is [col, row, value]
    wire = serialize_scent_for_cop({"4,3": 0.62, "0,0": 0.04})

    assert sorted(wire["cells"]) == sorted([[3, 4, 0.62], [0, 0, 0.04]])


def test_scent_round_trips_through_her_wire_shape():
    original = {"4,3": 0.62, "0,0": 0.04}
    assert deserialize_scent_from_cop(serialize_scent_for_cop(original)) == original


def test_deserialize_scent_from_cop_rejects_a_malformed_payload():
    import pytest

    with pytest.raises(ValueError, match="cells"):
        deserialize_scent_from_cop({"not_cells": []})
