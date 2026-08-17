"""The flat 14-key signed term set (spec Appendix A). Loaded verbatim from
a checked-in JSON file (config/thief/interop_spec_terms.json) rather than
derived from this repo's own nested config -- the spec requires the exact
JSON values *and types* (`0.1` as a JSON number, coordinates as integer
arrays, etc.), and any mapping/rounding step from our differently-shaped
config would risk silently producing different canonical bytes on our
side than on the other team's, breaking the signature and `game_uid`
without anything failing loudly.
"""

from __future__ import annotations

import json
from pathlib import Path

from thief_peer.exceptions import SimulationError

TERM_KEYS = (
    "board_size",
    "smell_grid_size",
    "decay_per_step",
    "emit_intensity",
    "min_center_intensity",
    "max_steps",
    "barriers_max",
    "setting",
    "hint_max_words",
    "axis_origin_corner",
    "axis_start_index",
    "thief_start",
    "cop_start",
    "num_games",
)

DEFAULT_TERMS_PATH = "config/thief/interop_spec_terms.json"


def load_terms(path: str | Path = DEFAULT_TERMS_PATH) -> dict:
    terms = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_terms(terms)
    return terms


def validate_terms(terms: object) -> None:
    """Spec Section 3's own greeting-validation rules 1-3, the local half
    (checking shape/completeness; a peer's terms differing from ours is
    checked by the caller, which has both sides to compare)."""
    if not isinstance(terms, dict):
        raise SimulationError("terms must be a JSON object")
    missing = [key for key in TERM_KEYS if key not in terms]
    if missing:
        raise SimulationError(f"terms missing required key(s): {missing}")
    extra = [key for key in terms if key not in TERM_KEYS]
    if extra:
        raise SimulationError(f"terms has unexpected key(s): {extra} -- the set is closed at 14")
