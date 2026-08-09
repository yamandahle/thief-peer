"""Wire shapes matching the Cop repo's actual `integrity/step0.py`,
`integrity/step0_wire.py`, and `tools/scent_wire.py` -- verified directly
against her cloned source, so a declaration/hash built here signs and
verifies identically on her side (empirically confirmed for
`scent_lock_hash`/`scent_model_sha256`: both sides independently compute
`5aac6e62703e2afffac1ad4738fa3f8e2c85da964dbf7a2de17fd3e00d516386` for the
book's default parameters).
"""

import hashlib
import json
import subprocess

from thief_peer.domain.crypto import hash_config_file  # noqa: F401 -- re-exported, see below

_VALUE_PRECISION = 2  # matches her Step0Declaration's ram_gb/gpu_vram_gb .2f convention

# hash_config_file used to be defined here as its own copy. Moved to
# domain/crypto.py (PRD_10) once domain/negotiation.py's native protocol
# needed the exact same byte-for-byte-file algorithm too -- re-exported
# under this name so every existing `from interop.cop_wire import
# hash_config_file` call site keeps working unchanged. Matches the Cop
# repo's own `integrity/step0.py::hash_config_file` exactly (empirically
# verified: for this to ever pass her side's `config_sha256` check, rule
# 11, our `game.json` must be byte-identical to hers, not just schema-
# identical -- a one-time coordination step, not something this function
# alone can guarantee).


def current_git_commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
    )
    return result.stdout.strip()


def build_cop_hardware(spec: dict, llm_model: str) -> dict:
    """`shared/sysinfo.py::collect_spec()`'s output, mapped onto her
    `HardwareDeclaration` field names/constraints (os_name non-empty,
    cpu_cores positive int, ram_gb non-negative float, llm_model
    non-empty)."""
    return {
        "os_name": spec["os"] or "unknown",
        "cpu_cores": spec["cpu_cores"] or 1,
        "ram_gb": spec["ram_gb"] or 0.01,
        "gpu_present": spec["gpu"] is not None,
        "gpu_vram_gb": spec["vram_gb"],
        "llm_model": llm_model or "none",
    }


def build_cop_declaration(
    *,
    hardware: dict,
    code_commit_hash: str,
    group_name: str,
    sub_game_number: int,
    config_sha256: str,
    scent_model_sha256: str,
) -> dict:
    """Matches her `integrity/step0_wire.py::declaration_to_wire` shape
    exactly -- what her `declaration_from_wire` expects to parse."""
    return {
        "hardware": hardware,
        "code_commit_hash": code_commit_hash,
        "group_name": group_name,
        "sub_game_number": sub_game_number,
        "config_sha256": config_sha256,
        "scent_model_sha256": scent_model_sha256,
    }


def sign_cop_declaration(declaration: dict) -> str:
    """Matches her `integrity/step0.py::sign_step0` exactly: ram_gb/
    gpu_vram_gb formatted as `.2f` strings before hashing (her own float-
    hash-drift mitigation), same field order/keys as her
    `_canonical_declaration_bytes`."""
    hardware = declaration["hardware"]
    payload = {
        "hardware": {
            "os_name": hardware["os_name"],
            "cpu_cores": hardware["cpu_cores"],
            "ram_gb": f"{hardware['ram_gb']:.{_VALUE_PRECISION}f}",
            "gpu_present": hardware["gpu_present"],
            "gpu_vram_gb": (
                None
                if hardware["gpu_vram_gb"] is None
                else f"{hardware['gpu_vram_gb']:.{_VALUE_PRECISION}f}"
            ),
            "llm_model": hardware["llm_model"],
        },
        "code_commit_hash": declaration["code_commit_hash"],
        "group_name": declaration["group_name"],
        "sub_game_number": declaration["sub_game_number"],
        "config_sha256": declaration["config_sha256"],
        "scent_model_sha256": declaration["scent_model_sha256"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def serialize_scent_for_cop(snapshot: dict[str, float]) -> dict:
    """Our `{"row,col": value}` -> her `{"cells": [[col, row, value], ...]}`
    (`tools/scent_wire.py::serialize_scent_field`)."""
    cells = []
    for key, value in snapshot.items():
        row, col = (int(part) for part in key.split(","))
        cells.append([col, row, value])
    return {"cells": cells}


def build_cop_state_string(row: int, col: int, steps_taken: int) -> str:
    """Matches her `integrity/commit_payload.py::canonical_state_bytes`
    byte-for-byte, for a thief-role agent specifically: `barriers_placed`
    is always `[]` (this side never places a barrier --
    `strategy/brain_base.py`'s own structural guarantee that
    `Decision.move_type` is never `BARRIER` for the thief role), `own_pos`
    is `[col, row]` (her `Position` field order, this side's own `Cell` is
    `(row, col)`). She reconstructs this independently by replaying this
    side's own revealed moves rather than trusting a transmitted `state`
    value (rule 27: never a position claim on the wire) -- so for her
    recomputed `Hcommit` to ever match what this side committed to, this
    side's own hashed `state` must equal exactly what her replay would
    derive, not an arbitrary local label. Returns a `str`, not `bytes`,
    because her own `_canonical_envelope_bytes` decodes her `state: bytes`
    field to utf-8 before hashing -- this is that already-decoded string."""
    payload = {"own_pos": [col, row], "steps_taken": steps_taken, "barriers_placed": []}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_cop_move_envelope(direction: str) -> dict:
    """This side's own sealed envelope must hash the same `move` shape she
    receives over `receive_reveal` and stores in her `PeerTrace` (her own
    `move_to_wire` output, `{"type": "move", "direction": ...}`) -- not the
    bare direction string this side uses internally everywhere else.
    Thief never places a barrier (see `build_cop_state_string`), so this is
    always a `move`, never a `place_barrier`, envelope."""
    return {"type": "move", "direction": direction}


def build_cop_final_reveal_payload(records: list[dict]) -> tuple[dict, dict]:
    """This side's own revealed nonces/intents, keyed by step (as strings --
    JSON object keys are always strings), matching her `receive_final_reveal`
    contract. Meaningful now that `peer/sealing.py::sealed_step_record`
    hashes the same 7-field shape her `integrity/commit_reveal.py::
    CommitEnvelope` does (state, move, intent, nonce, hint_text, step,
    role) -- her side's own audit can genuinely recompute and verify this
    peer's per-turn Hcommit from this data. `intent` must already be a real
    `bool` in `payload["intent"]` by the time it reaches here (see
    `interop/cop_round_loop.py`) -- her own `integrity/peer_trace.py::
    run_peer_audit` does `intent=bool(entry.intent)` on whatever arrives,
    and a non-empty string ("truth" *or* "lie") is truthy either way, which
    would silently corrupt her reconstruction rather than raise."""
    nonces: dict[str, str] = {}
    intents: dict[str, bool] = {}
    for record in records:
        payload = record["payload"]
        step_key = str(payload["step"])
        nonces[step_key] = payload["nonce"]
        intents[step_key] = bool(payload["intent"])
    return nonces, intents


def deserialize_scent_from_cop(wire: dict) -> dict[str, float]:
    """The inverse of `serialize_scent_for_cop` -- her `{"cells": [[col,
    row, value], ...]}` -> our `{"row,col": value}`, ready for
    `ScentField.absorb`."""
    if not isinstance(wire, dict) or not isinstance(wire.get("cells"), list):
        raise ValueError(f"scent-map payload missing a 'cells' list: {wire!r}")
    result: dict[str, float] = {}
    for entry in wire["cells"]:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise ValueError(f"malformed scent-map cell entry: {entry!r}")
        col, row, value = entry
        result[f"{row},{col}"] = float(value)
    return result
