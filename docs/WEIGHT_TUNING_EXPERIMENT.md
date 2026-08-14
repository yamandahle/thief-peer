# Weight-tuning experiment (backlog item 18)

**Status: DONE. `expected_distance_weight = 2.0` is rejected, not
adopted.** All current constants in `fleeing_brain.py` are unchanged. Step
(d) (verification before adoption) found a faster, more decisive signal
than a live match and didn't need one — see "Step (d)" below.

## Why this needed redoing

On 2026-08-12, `scripts/tune_weights.py` found a configuration (higher
`EXPECTED_DISTANCE_WEIGHT`) that scored 77% simulated win rate. It was
hand-applied to `fleeing_brain.py`, then reverted the same day: 6 real
matches against the actual Cop repo produced 5 losses, all via the Thief
repeatedly choosing STAY in a corner (the single farthest cell from the
believed Cop position under that weighting) while the real Cop walled it
in with barriers. The simulator that produced the 77% number could never
place a barrier at all, so it could never punish that exact pattern —
the good score was an artifact of an incomplete opponent model, not a real
improvement. Full account: `fleeing_brain.py`'s own `REVERTED` comment.

## What changed before re-running

1. **`scripts/tuning_cop.py`**: `book_baseline_cop_decision` now walls the
   Thief in — when the believed Thief cell is Manhattan-distance 1 from
   the Cop, it places a barrier there instead of moving (capped at the
   real 14-barrier limit). `simulate_match` gained `cop_places_barriers`
   and keeps the Thief's own `known_barriers` in sync each round, the same
   way the real `handle_receive_barrier_declaration` flow does. Verified
   directly (not just by the sweep) with a scripted always-STAY Thief
   pinned in a corner against this new Cop: captured by step 3, confirming
   the fix actually punishes the exact pattern that broke the last attempt.
2. The Thief's own scent snapshot is now fed into `decide()` during
   simulation too, so `scent_weight` (item 15, not yet empirically tuned)
   is actually exercised by the sweep, not left at its reasoned-but-guessed
   default the whole time.
3. `scent_weight` added to `CANDIDATES`/`DEFAULTS`.

## Result

30 trials/config, 2-pass coordinate ascent, seed `20260814`. Full raw
numbers (every candidate value tried, not just the winners) in
`docs/weight_tuning_results.json`.

| | win rate vs barrier-placing Cop (tuning signal) | mean capture step | win rate vs barrier-free Cop (context only) |
|---|---|---|---|
| Starting defaults | 0.33 | 12.9 | 0.30 |
| Final chosen | **0.83** | 23.8 | 0.63 |

Final chosen configuration:

```
expected_distance_weight = 2.0   (was 1.0)
mobility_weight          = 1.5   (unchanged)
lookahead_weight         = 0.1   (unchanged)
lookahead_candidate_count = 5    (unchanged, all 4 candidates tied)
scent_weight             = 0.5   (unchanged, tied with 1.0)
```

## Why this is not being hand-applied yet

`expected_distance_weight = 2.0` is **the same knob, in the same
direction**, that the 2026-08-12 regression already burned once. The
simulator is meaningfully more honest now (it discriminates: 33%/83%, not
saturated at 0% or 100%, and the barrier-placing fix is independently
verified against a scripted camper, not just trusted because the sweep
says so) — but "a more honest simulator still says push this knob up" is
not the same claim as "this is safe in a real match." The exact failure
mode last time was a simulator blind spot that made a real vulnerability
look like a strength; a *different* blind spot in the new simulator
(a simple distance-1 barrier heuristic is still a much cruder threat model
than a real, possibly-adaptive Cop) could do the same thing again in a way
this sweep can't see. Per this backlog item's own sequencing plan (step
(d)), the only real check is playing it against the actual Cop repo before
touching `fleeing_brain.py`'s constants.

## Step (d): verification, and why a live match wasn't needed

Before spending a real match on this, `expected_distance_weight` was set
to `2.0` locally (temporarily, never committed) and the existing test
suite was re-run. Two tests **failed immediately**, both specifically
designed to catch the exact 2026-08-12 failure mode (mobility-aware
corner-avoidance losing to raw distance-maximization):

```
FAILED test_beats_naive_single_peak_baseline_over_a_scripted_chase
  assert smart_avg > naive_avg  ->  assert 1.7 > 1.7
FAILED test_corner_avoidance_prefers_higher_mobility_over_raw_distance
  assert naive_mobility < smart_mobility  ->  assert 3 < 3
```

At `2.0`, `ThiefBrain` ties the naive single-peak baseline on both of its
own advantages over that baseline — the exact mechanism (mobility-aware
scoring losing to distance-maximization) that made the Thief camp in
corners and lose 5/6 real matches on 2026-08-12. This is a deterministic,
mechanism-level reproduction of the known failure, not a single noisy
match outcome — arguably stronger evidence than one live match would have
been, and found in well under a second instead of a full 35-round match.
The weight was reverted to `1.0` immediately; `fleeing_brain.py`'s
constants were never actually changed in git.

**Conclusion: `expected_distance_weight = 2.0` is rejected.** All of
`fleeing_brain.py`'s constants stay at their current values
(`expected_distance_weight=1.0`, `mobility_weight=1.5`,
`lookahead_weight=0.1`, `lookahead_candidate_count=5`,
`scent_weight=0.5`) — the same values already in place before this
experiment. The rebuilt simulator and this sweep didn't find a safe
improvement; they found (and this time caught, before a real match had
to pay for it) the same trap the 2026-08-12 attempt walked into. That's
still a real, useful result: the simulator fix (barrier placement) plus
this cheap test-suite cross-check is now a reusable, fast way to
sanity-check any future weight candidate before ever risking a real match
on it.

## Step (e): README write-up

Deferred, but for a different reason than originally planned — not
"pending a positive result to write up," but because the honest
conclusion here (redid the experiment properly, still didn't find a safe
improvement, and caught why fast) is itself worth writing into the
report's "dilemmas" section once, well-framed, rather than piecemeal.
Tracked as `README_PLAN.md` item 8.
