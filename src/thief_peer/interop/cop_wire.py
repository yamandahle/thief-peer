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
from pathlib import Path

_VALUE_PRECISION = 2  # matches her Step0Declaration's ram_gb/gpu_vram_gb .2f convention


def hash_config_file(path: str | Path) -> str:
    """Plain sha256(raw bytes) -- matches her `integrity/step0.py::
    hash_config_file` and her `check_config.py --identical`. For this to
    ever pass her side's `config_sha256` check (rule 11), our `game.json`
    must be byte-identical to her shared config file, not just schema-
    identical -- a one-time coordination step, not something this function
    alone can guarantee."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
