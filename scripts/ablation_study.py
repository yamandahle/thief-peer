"""Heuristic ablation study, run by direct request after backlog item 18:
tune_weights.py answers "what's the best combined setting" -- this answers
the different question "how much does each individual signal actually
matter." Turns each of ThiefBrain's weighted signals off one at a time
(weight -> 0.0, everything else left at the shipped defaults) and compares
against the book's own naive single-peak baseline and the full combined
brain, all through the exact same barrier-placing book-baseline Cop
tune_weights.py's own sweep already established as the only opponent whose
numbers are trustworthy here (see tuning_cop.py's module docstring --
a barrier-free simulator can't punish corner-camping at all).

Dev tooling only -- run manually with
`uv run python scripts/ablation_study.py`. Saves full results to
`docs/heuristic_ablation_results.json`; see `docs/HEURISTIC_ABLATION.md`
for the write-up.
"""

import json
import random
import time
from pathlib import Path

from tuning_cop import NaiveBrain, simulate_match

from thief_peer.domain.board import Board
from thief_peer.strategy.fleeing_brain import (
    EXPECTED_DISTANCE_WEIGHT,
    LOOKAHEAD_CANDIDATE_COUNT,
    LOOKAHEAD_WEIGHT,
    MOBILITY_WEIGHT,
    SCENT_WEIGHT,
)

BOARD_SIZE = 7
MAX_MOVES = 35
TRIALS_PER_CONFIG = 100
SEED_BASE = 20260815
RESULTS_PATH = Path(__file__).resolve().parent.parent / "docs" / "heuristic_ablation_results.json"

DEFAULTS = {
    "expected_distance_weight": EXPECTED_DISTANCE_WEIGHT,
    "mobility_weight": MOBILITY_WEIGHT,
    "lookahead_weight": LOOKAHEAD_WEIGHT,
    "lookahead_candidate_count": LOOKAHEAD_CANDIDATE_COUNT,
    "scent_weight": SCENT_WEIGHT,
}

# (label, weights dict or None -> None means "use NaiveBrain instead").
# Order matters for the printed table and the saved JSON, not the results.
CONFIGURATIONS = [
    ("naive_single_peak_baseline", None),
    ("expected_distance_only", {**DEFAULTS, "mobility_weight": 0.0, "lookahead_weight": 0.0, "scent_weight": 0.0}),
    ("no_mobility_signal", {**DEFAULTS, "mobility_weight": 0.0}),
    ("no_lookahead_signal", {**DEFAULTS, "lookahead_weight": 0.0}),
    ("no_scent_signal", {**DEFAULTS, "scent_weight": 0.0}),
    ("full_thiefbrain_shipped_defaults", dict(DEFAULTS)),
]


def _random_trial_setup(rng: random.Random, size: int):
    """Identical to tune_weights.py's own helper -- kept as its own copy
    (not imported) since this script is meant to be read and run standalone,
    same as tune_weights.py already is."""
    while True:
        thief_start = (rng.randrange(size), rng.randrange(size))
        cop_start = (rng.randrange(size), rng.randrange(size))
        if abs(thief_start[0] - cop_start[0]) + abs(thief_start[1] - cop_start[1]) >= size:
            break
    barriers = set()
    if rng.random() < 0.5:
        for _ in range(rng.randint(1, 4)):
            cell = (rng.randrange(size), rng.randrange(size))
            if cell not in (thief_start, cop_start):
                barriers.add(cell)
    return thief_start, cop_start, barriers


def run_configuration(weights: dict | None, seed: int) -> dict:
    rng = random.Random(seed)
    wins = 0
    capture_steps = []
    for _ in range(TRIALS_PER_CONFIG):
        thief_start, cop_start, barriers = _random_trial_setup(rng, BOARD_SIZE)
        board = Board(size=BOARD_SIZE, barriers=barriers)
        thief_brain = NaiveBrain() if weights is None else None
        outcome = simulate_match(
            weights or {},
            True,
            board,
            thief_start,
            cop_start,
            MAX_MOVES,
            cop_places_barriers=True,
            thief_brain=thief_brain,
        )
        if outcome is None:
            wins += 1
        else:
            capture_steps.append(outcome)
    return {
        "win_rate": wins / TRIALS_PER_CONFIG,
        "mean_capture_step": sum(capture_steps) / len(capture_steps) if capture_steps else None,
        "captures": len(capture_steps),
        "survivals": wins,
    }


def main() -> dict:
    started_at = time.monotonic()
    results = {}
    print(f"Heuristic ablation study -- {TRIALS_PER_CONFIG} trials/config vs the barrier-placing book-baseline Cop\n")
    for label, weights in CONFIGURATIONS:
        stats = run_configuration(weights, seed=SEED_BASE)
        results[label] = {"weights": weights, **stats}
        capture = f"{stats['mean_capture_step']:.1f}" if stats["mean_capture_step"] is not None else "n/a"
        print(f"{label:<35} win_rate={stats['win_rate']:.2f}  mean_capture_step={capture}")

    elapsed = time.monotonic() - started_at
    print(f"\n({TRIALS_PER_CONFIG} trials/config, {elapsed:.1f}s total)")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "seed_base": SEED_BASE,
                "trials_per_config": TRIALS_PER_CONFIG,
                "board_size": BOARD_SIZE,
                "max_moves": MAX_MOVES,
                "configurations": results,
                "elapsed_seconds": elapsed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved full results to {RESULTS_PATH}")
    return results


if __name__ == "__main__":
    main()
