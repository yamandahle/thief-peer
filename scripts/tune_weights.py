"""Empirical coordinate-ascent sweep over ThiefBrain's weight constants.
Tuning signal is win rate against the book-baseline opponent only (real
scent + belief, the one realistic stand-in -- see tuning_cop.py's
book_baseline_cop_move). The scripted-chase "naive" opponent cheats via
exact real-position tracking, which book rule 27 forbids any real Cop from
doing, so it can't meaningfully drive a win/lose tuning signal (it
saturates at 0% regardless of weights on a small board); it's reported
separately, before/after, purely as the same average-distance-maintained
sanity check tests/unit/test_fleeing_brain.py already uses it for.

Dev tooling only -- run manually with `uv run python scripts/tune_weights.py`,
review the printed table, then hand-apply the winning values to
fleeing_brain.py's constants.
"""

import random

from tuning_cop import average_distance_vs_naive_pursuer, simulate_match

from thief_peer.domain.board import Board
from thief_peer.strategy.fleeing_brain import (
    EXPECTED_DISTANCE_WEIGHT,
    LOOKAHEAD_CANDIDATE_COUNT,
    LOOKAHEAD_WEIGHT,
    MOBILITY_WEIGHT,
)

BOARD_SIZE = 7
MAX_MOVES = 35
TRIALS_PER_CONFIG = 30
SEED_BASE = 20260812

CANDIDATES = {
    "expected_distance_weight": [0.5, 1.0, 1.5, 2.0],
    "mobility_weight": [0.5, 1.0, 1.5, 2.0, 3.0],
    "lookahead_weight": [0.0, 0.1, 0.3, 0.5, 1.0],
    "lookahead_candidate_count": [1, 3, 5, 10],
}

DEFAULTS = {
    "expected_distance_weight": EXPECTED_DISTANCE_WEIGHT,
    "mobility_weight": MOBILITY_WEIGHT,
    "lookahead_weight": LOOKAHEAD_WEIGHT,
    "lookahead_candidate_count": LOOKAHEAD_CANDIDATE_COUNT,
}


def _random_trial_setup(rng: random.Random, size: int):
    """Start positions kept at least half the board apart; half the trials
    also get a handful of static barriers, for variety."""
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


def book_baseline_win_rate(weights: dict, seed: int = SEED_BASE) -> float:
    rng = random.Random(seed)
    wins = 0
    for _ in range(TRIALS_PER_CONFIG):
        thief_start, cop_start, barriers = _random_trial_setup(rng, BOARD_SIZE)
        board = Board(size=BOARD_SIZE, barriers=barriers)
        outcome = simulate_match(weights, True, board, thief_start, cop_start, MAX_MOVES)
        if outcome is None:
            wins += 1
    return wins / TRIALS_PER_CONFIG


def naive_avg_distance(weights: dict, seed: int = SEED_BASE + 2_000_000) -> float:
    rng = random.Random(seed)
    total = 0.0
    for _ in range(TRIALS_PER_CONFIG):
        thief_start, cop_start, barriers = _random_trial_setup(rng, BOARD_SIZE)
        board = Board(size=BOARD_SIZE, barriers=barriers)
        total += average_distance_vs_naive_pursuer(
            weights, board, thief_start, cop_start, MAX_MOVES
        )
    return total / TRIALS_PER_CONFIG


def coordinate_ascent() -> dict:
    current = dict(DEFAULTS)
    start_score = book_baseline_win_rate(current)
    start_naive_avg = naive_avg_distance(current)
    print(f"Starting defaults: {current}")
    print(f"  win rate vs book-baseline={start_score:.2f}")
    print(f"  avg distance vs naive (sanity check only)={start_naive_avg:.2f}\n")

    for pass_num in (1, 2):
        print(f"=== Pass {pass_num} ===")
        for param, candidates in CANDIDATES.items():
            best_value = current[param]
            best_score = book_baseline_win_rate(current)
            print(f"\nTuning {param} (currently {best_value}):")
            for value in candidates:
                trial = {**current, param: value}
                score = book_baseline_win_rate(trial)
                marker = ""
                if score > best_score:
                    best_score, best_value, marker = score, value, "  <- new best"
                print(f"  {param}={value}: win_rate={score:.2f}{marker}")
            current[param] = best_value

    final_score = book_baseline_win_rate(current)
    final_naive_avg = naive_avg_distance(current)
    print(f"\n=== Final chosen configuration ===\n{current}")
    print(f"win rate vs book-baseline={final_score:.2f} (was {start_score:.2f})")
    print(f"avg distance vs naive, sanity check only={final_naive_avg:.2f} (was {start_naive_avg:.2f})")
    return current


if __name__ == "__main__":
    coordinate_ascent()
