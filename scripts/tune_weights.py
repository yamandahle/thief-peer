"""Empirical coordinate-ascent sweep over ThiefBrain's weight constants.
Tuning signal is win rate against the book-baseline, *barrier-placing*
opponent (real scent + belief, plus tuning_cop.py's
book_baseline_cop_decision walling the Thief in when adjacent to the
believed position) -- closing this script's own 2026-08-12 post-mortem
(fleeing_brain.py's revert note): the previous sweep's opponent could never
place a barrier, so it could never punish corner-camping, and the
"winning" configuration it found made real matches worse, not better. The
old barrier-free win rate is still reported alongside, for context only --
never what picks a winner now. The scripted-chase "naive" opponent cheats
via exact real-position tracking, which book rule 27 forbids any real Cop
from doing, so it can't meaningfully drive a win/lose tuning signal either
(it saturates at 0% regardless of weights on a small board); it's reported
separately, before/after, purely as the same average-distance-maintained
sanity check tests/unit/test_fleeing_brain.py already uses it for.

Dev tooling only -- run manually with `uv run python scripts/tune_weights.py`,
review the printed table and the saved `docs/weight_tuning_results.json`,
then hand-apply the winning values to fleeing_brain.py's constants --
*only* after verifying the simulated winner against real matches (item
18(d); a good simulated score alone was exactly what went wrong last time).
"""

import json
import random
import time
from pathlib import Path

from tuning_cop import average_distance_vs_naive_pursuer, simulate_match

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
TRIALS_PER_CONFIG = 30
SEED_BASE = 20260814
RESULTS_PATH = Path(__file__).resolve().parent.parent / "docs" / "weight_tuning_results.json"

CANDIDATES = {
    "expected_distance_weight": [0.5, 1.0, 1.5, 2.0],
    "mobility_weight": [0.5, 1.0, 1.5, 2.0, 3.0],
    "lookahead_weight": [0.0, 0.1, 0.3, 0.5, 1.0],
    "lookahead_candidate_count": [1, 3, 5, 10],
    "scent_weight": [0.0, 0.25, 0.5, 1.0, 2.0],
}

DEFAULTS = {
    "expected_distance_weight": EXPECTED_DISTANCE_WEIGHT,
    "mobility_weight": MOBILITY_WEIGHT,
    "lookahead_weight": LOOKAHEAD_WEIGHT,
    "lookahead_candidate_count": LOOKAHEAD_CANDIDATE_COUNT,
    "scent_weight": SCENT_WEIGHT,
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


def book_baseline_win_rate(weights: dict, seed: int = SEED_BASE, cop_places_barriers: bool = True) -> dict:
    """Primary tuning signal (`cop_places_barriers=True`, the default).
    Returns win_rate plus the mean capture step among losses (None-safe --
    `None` when every trial survived), item 18(c)'s "survival/capture
    numbers," not win rate alone."""
    rng = random.Random(seed)
    wins = 0
    capture_steps = []
    for _ in range(TRIALS_PER_CONFIG):
        thief_start, cop_start, barriers = _random_trial_setup(rng, BOARD_SIZE)
        board = Board(size=BOARD_SIZE, barriers=barriers)
        outcome = simulate_match(
            weights, True, board, thief_start, cop_start, MAX_MOVES,
            cop_places_barriers=cop_places_barriers,
        )
        if outcome is None:
            wins += 1
        else:
            capture_steps.append(outcome)
    return {
        "win_rate": wins / TRIALS_PER_CONFIG,
        "mean_capture_step": sum(capture_steps) / len(capture_steps) if capture_steps else None,
    }


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


def _fmt(stats: dict) -> str:
    capture = f"{stats['mean_capture_step']:.1f}" if stats["mean_capture_step"] is not None else "n/a"
    return f"win_rate={stats['win_rate']:.2f} (mean capture step={capture})"


def coordinate_ascent() -> dict:
    started_at = time.monotonic()
    current = dict(DEFAULTS)
    start_stats = book_baseline_win_rate(current)
    start_no_barrier = book_baseline_win_rate(current, cop_places_barriers=False)
    start_naive_avg = naive_avg_distance(current)
    print(f"Starting defaults: {current}")
    print(f"  vs barrier-placing book-baseline (tuning signal): {_fmt(start_stats)}")
    print(f"  vs barrier-free book-baseline (context only):     {_fmt(start_no_barrier)}")
    print(f"  avg distance vs naive (sanity check only)={start_naive_avg:.2f}\n")

    history = []
    for pass_num in (1, 2):
        print(f"=== Pass {pass_num} ===")
        for param, candidates in CANDIDATES.items():
            best_value = current[param]
            best_stats = book_baseline_win_rate(current)
            print(f"\nTuning {param} (currently {best_value}):")
            for value in candidates:
                trial = {**current, param: value}
                stats = book_baseline_win_rate(trial)
                marker = ""
                if stats["win_rate"] > best_stats["win_rate"]:
                    best_stats, best_value, marker = stats, value, "  <- new best"
                print(f"  {param}={value}: {_fmt(stats)}{marker}")
                history.append({"pass": pass_num, "param": param, "value": value, **stats})
            current[param] = best_value

    final_stats = book_baseline_win_rate(current)
    final_no_barrier = book_baseline_win_rate(current, cop_places_barriers=False)
    final_naive_avg = naive_avg_distance(current)
    elapsed = time.monotonic() - started_at
    print(f"\n=== Final chosen configuration ===\n{current}")
    print(f"vs barrier-placing book-baseline (tuning signal): {_fmt(final_stats)} (was {_fmt(start_stats)})")
    print(f"vs barrier-free book-baseline (context only):     {_fmt(final_no_barrier)} (was {_fmt(start_no_barrier)})")
    print(f"avg distance vs naive, sanity check only={final_naive_avg:.2f} (was {start_naive_avg:.2f})")
    print(f"({TRIALS_PER_CONFIG} trials/config, {elapsed:.1f}s total)")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "seed_base": SEED_BASE,
                "trials_per_config": TRIALS_PER_CONFIG,
                "defaults": DEFAULTS,
                "start_vs_barrier_placing": start_stats,
                "start_vs_barrier_free": start_no_barrier,
                "start_naive_avg_distance": start_naive_avg,
                "final_chosen": current,
                "final_vs_barrier_placing": final_stats,
                "final_vs_barrier_free": final_no_barrier,
                "final_naive_avg_distance": final_naive_avg,
                "history": history,
                "elapsed_seconds": elapsed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved full results to {RESULTS_PATH}")
    return current


if __name__ == "__main__":
    coordinate_ascent()
