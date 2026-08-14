# Heuristic ablation study

**What this answers, and what it doesn't.** `docs/WEIGHT_TUNING_EXPERIMENT.md`
(item 18) asked "what's the best combined weight setting" and rejected its
top candidate. This is a different question: **how much does each
individual signal actually contribute**, holding everything else at the
shipped defaults. Run by direct request, separate from the numbered
backlog. Same barrier-placing book-baseline Cop as item 18 (the only
opponent whose numbers are trustworthy here — see `tuning_cop.py`'s own
docstring for why a barrier-free simulator can't be trusted).

**No weights have been changed.** This is a measurement, not a decision —
see "What this doesn't mean" below before drawing conclusions from it.

## Method

`scripts/ablation_study.py`: 100 trials/config, `seed_base=20260815`, 7×7
board, 35-move ceiling, randomized start positions and static barriers per
trial (identical setup to `tune_weights.py`). Each configuration is the
shipped defaults (`expected_distance_weight=1.0, mobility_weight=1.5,
lookahead_weight=0.1, lookahead_candidate_count=5, scent_weight=0.5`) with
exactly one signal's weight zeroed, plus the book's own naive single-peak
baseline (`NaiveBrain`, no mobility/lookahead/scent at all) and a
distance-only configuration (every other signal zeroed) as floor/ceiling
references. Full raw output: `docs/heuristic_ablation_results.json`.

## Result

| Configuration | win rate | mean capture step |
|---|---|---|
| naive single-peak baseline (book default) | 0.01 | 12.4 |
| expected-distance only (all else zeroed) | 0.00 | 10.1 |
| **no mobility signal** | **0.62** | 11.2 |
| no lookahead signal | 0.10 | 18.1 |
| no scent signal | 0.00 | 11.2 |
| **full ThiefBrain (shipped defaults)** | **0.34** | 13.9 |

Cross-checked against 3 additional random seeds (99, 4242, 777) to rule
out a lucky draw — the same pattern held every time:

| seed | full win rate | no-mobility win rate |
|---|---|---|
| 99 | 0.26 | 0.64 |
| 4242 | 0.32 | 0.53 |
| 777 | 0.31 | 0.73 |

Three findings, in order of how much they should change anything:

1. **Scent-avoidance (item 15) is the single biggest contributor.**
   Zeroing it alone drops the win rate from 0.34 to 0.00 — worse than
   distance-only. Directly confirms the book's own ch.1.4 framing
   (staying/returning only ever costs you) was worth building.
2. **Lookahead (the 1-ply expectimax) meaningfully helps.** Zeroing it
   drops win rate from 0.34 to 0.10.
3. **Mobility consistently *hurts* against this specific Cop, every
   seed tried.** Removing it nearly doubles the win rate.

## What this doesn't mean

Finding 3 is real and reproducible, but "delete `MOBILITY_WEIGHT`" would
repeat the exact mistake `WEIGHT_TUNING_EXPERIMENT.md` just finished
warning about: one simulated signal, however consistent, isn't proof
something is safe to change in a system with a documented history of a
simulator blind spot causing a real-match regression.

The likely mechanism: `MOBILITY_WEIGHT=1.5` is the single largest weight
in the sum, and it rewards cells with many open neighbors — mostly the
board's interior. `book_baseline_cop_decision` (item 18) walls the Thief
in specifically when it gets *adjacent* to the believed position, a
proximity threat, not a dead-end threat. A high mobility weight can keep
the Thief content to loiter in open, easy-to-navigate territory rather
than actually gaining distance, which is the wrong response to a
proximity-triggered threat specifically — but mobility was originally
added for a *different*, still-real danger (`test_corner_avoidance_
prefers_higher_mobility_over_raw_distance`'s own literal dead-end pocket),
which this particular Cop model doesn't test at all. Two different
threats, one weight, one simulated opponent that only exercises one of
them — exactly the kind of blind spot item 18 already burned once on.

**Not acting on this without the same discipline item 18 used**: cross-
check any candidate change against the existing behavioral test suite
(the dead-end test above is the fast, free check that already exists),
and treat a single ablation result as a lead to investigate, not a
weight to hand-apply.
