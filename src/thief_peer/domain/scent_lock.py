"""Ch.4.5's scent-lock ceremony (rule 23, FATAL): hashes the pheromone
formula's *shape* together with its numbers and a computed worked example,
so two independently-built ScentField implementations that happen to share
identical config values but differ in kernel layout, decay order, or
rounding still produce different hashes and get caught before move 1.
`negotiation.py`'s CANONICAL_TERM_KEYS already locks the three raw numbers
via Commit-Reveal; this catches implementation drift the numbers alone
can't (the book's own example: 0.9 -> 0.81 under the default decay rate).

The worked-example construction below (synthetic 9x9 board, deposit at
(4,4) then (0,0), sample the center before/after the second decay round,
.10f precision, canonical JSON) matches the Cop repo's own
`integrity/scent_model_lock.py` byte-for-byte, deliberately -- so the two
independently-computed hashes are directly comparable once exchanged via
the Cop interop adapter (Step-0's `scent_model_sha256` field), not just
parallel constructions that happen to look similar. Read directly from
her source rather than re-derived, per this project's "verify empirically"
discipline.
"""

import hashlib

from thief_peer.domain.crypto import canonical_json
from thief_peer.domain.scent import ScentField

_VALUE_PRECISION = 10

# Fixed formula shape (ch.4.3/Figure 4) -- same string on every match
# regardless of configured numbers, so a peer running a differently-shaped
# formula (not just different numbers) still produces a different hash.
FORMULA_DESCRIPTION = (
    "tau(t+1) = max(0, (1-rho)*tau(t) + delta_tau); "
    "delta_tau is a fixed radial 5x5 kernel (Figure 4) centered on the "
    "emitting cell, scaled by source_strength/0.9"
)

# Oversized purely so the kernel never clips against a board edge -- has no
# relationship to any real match's configured grid_size. _FAR_CELL is more
# than one kernel radius (2) away from _SYNTHETIC_CENTER on both axes, so a
# deposit at one never touches the other's cell.
_SYNTHETIC_BOARD_SIZE = 9
_SYNTHETIC_CENTER: tuple[int, int] = (4, 4)
_FAR_CELL: tuple[int, int] = (0, 0)


def _sample(field: ScentField, cell: tuple[int, int]) -> float:
    row, col = cell
    return field.snapshot().get(f"{row},{col}", 0.0)


def _worked_numeric_example(center_intensity: float, decay_rate: float) -> dict:
    """Emit once at the synthetic center, then emit again at a far cell
    (far enough its own fresh deposit never overlaps the center) so the
    second reading reflects pure decay of the first deposit, not decay
    plus a new deposit landing on the same cell."""
    field = ScentField(_SYNTHETIC_BOARD_SIZE, center_intensity, decay_rate)
    field.advance(_SYNTHETIC_CENTER)
    center_after_emission = _sample(field, _SYNTHETIC_CENTER)
    field.advance(_FAR_CELL)
    center_after_one_decay_round = _sample(field, _SYNTHETIC_CENTER)
    return {
        "center_after_emission": f"{center_after_emission:.{_VALUE_PRECISION}f}",
        "center_after_one_decay_round": f"{center_after_one_decay_round:.{_VALUE_PRECISION}f}",
    }


def scent_lock_payload(center_intensity: float, decay_rate: float, field_size: int) -> dict:
    return {
        "formula_description": FORMULA_DESCRIPTION,
        "source_strength": f"{center_intensity:.{_VALUE_PRECISION}f}",
        "decay_rate": f"{decay_rate:.{_VALUE_PRECISION}f}",
        "field_size": field_size,
        "worked_numeric_example": _worked_numeric_example(center_intensity, decay_rate),
    }


def scent_lock_hash(center_intensity: float, decay_rate: float, field_size: int) -> str:
    """SHA-256 of the canonical formula-shape + numbers + worked-example
    payload -- this repo's own answer to ch.4.5's "lock it cryptographically"
    instruction."""
    payload = scent_lock_payload(center_intensity, decay_rate, field_size)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
