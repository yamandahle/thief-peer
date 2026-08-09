"""interop/cop_wire.py tests. The pinned hashes below were verified
empirically against the Cop repo's own cloned source
(`integrity/step0.py::sign_step0`, `integrity/scent_model_lock.py::
compute_scent_model_hash`, `integrity/commit_reveal.py::commit` +
`integrity/commit_payload.py::canonical_state_bytes`) producing
byte-identical output for the same inputs -- not just self-consistency,
real cross-repo agreement."""

from thief_peer.domain.crypto import CommitReveal
from thief_peer.interop.cop_wire import (
    build_cop_declaration,
    build_cop_final_reveal_payload,
    build_cop_hardware,
    build_cop_move_envelope,
    build_cop_state_string,
    deserialize_scent_from_cop,
    serialize_scent_for_cop,
    sign_cop_declaration,
)

_KNOWN_GOOD_SIGNATURE = "432f16e658a3c12d1324012ab1799180c32ff03e6a28e7608883ed3540ae944c"

# Computed by actually running her real, cloned source (2026-08-09):
#   from cop.integrity.commit_reveal import CommitEnvelope, commit
#   from cop.integrity.commit_payload import canonical_state_bytes
#   from cop.reasoning.state import GameState, ground_truth_target_position
#   from cop.domain.barriers import BarrierSet
#   from cop.domain.board import Position
#   game_state = GameState(own_pos=Position(col=3, row=2),
#                           target_pos=ground_truth_target_position(Position(col=3, row=2)),
#                           barriers=BarrierSet(quota=14))
#   game_state.steps_taken = 1
#   envelope = CommitEnvelope(state=canonical_state_bytes(game_state),
#                              move={"type": "move", "direction": "N"}, intent=True,
#                              nonce="deadbeef", hint_text="cold", step=1, role="thief")
#   commit(envelope)  ->  the value below
_KNOWN_GOOD_COMMIT = "11516c3acdbef650c7ddedb1ce20483ee367b2fae20310485f37c6b8bbf1dacf"


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


def test_build_cop_state_string_matches_her_canonical_state_bytes_reconstruction():
    # She reconstructs own_pos as [col, row] with steps_taken=1 after this
    # peer moved N once from (col=3, row=3) to (col=3, row=2); thief never
    # places a barrier, so barriers_placed is always [].
    assert (
        build_cop_state_string(row=2, col=3, steps_taken=1)
        == '{"barriers_placed":[],"own_pos":[3,2],"steps_taken":1}'
    )


def test_our_own_sealed_envelope_produces_the_identical_hash_her_commit_would():
    """The real cross-repo check: seal a turn exactly the way
    interop/cop_round_loop.py::play_round_cop does (state via
    build_cop_state_string, move via build_cop_move_envelope, intent
    booleanized) and confirm the resulting commit is byte-identical to her
    own commit() over the equivalent CommitEnvelope -- not just that our two
    functions agree with each other, but that a peer running her real,
    independently-built audit code would recompute the exact same hash."""
    payload = {
        "state": build_cop_state_string(row=2, col=3, steps_taken=1),
        "move": build_cop_move_envelope("N"),
        "intent": True,
        "hint_text": "cold",
        "step": 1,
        "role": "thief",
    }
    assert CommitReveal.commit_of(payload, "deadbeef") == _KNOWN_GOOD_COMMIT


def test_build_cop_move_envelope_matches_her_move_to_wire_shape():
    assert build_cop_move_envelope("STAY") == {"type": "move", "direction": "STAY"}


def test_build_cop_final_reveal_payload_booleanizes_intent_and_keys_by_step_string():
    records = [
        {"payload": {"step": 1, "nonce": "n1", "intent": True}},
        {"payload": {"step": 2, "nonce": "n2", "intent": False}},
    ]

    nonces, intents = build_cop_final_reveal_payload(records)

    assert nonces == {"1": "n1", "2": "n2"}
    assert intents == {"1": True, "2": False}
    assert all(isinstance(v, bool) for v in intents.values())
