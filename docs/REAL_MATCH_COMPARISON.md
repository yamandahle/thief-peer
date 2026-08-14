# Real-match parameter comparison

**By direct request, separate from the numbered backlog**: actual real
games against the real Cop (her live `RLCopBrain` + promoted checkpoint,
not a simulation), not a proxy metric — the whole point being that this
project has already been burned once by trusting a simulator's win rate
over real match behavior (`docs/WEIGHT_TUNING_EXPERIMENT.md`).

## Method

`scripts/real_match_harness.py` launches both real processes locally
(cop_v1 protocol, `config/cop_rl_local_test.toml` on this side selecting
her real `RLCopBrain` — kept entirely in this repo, nothing in her working
directory touched) for each of 4 weight configurations, records the real
win/loss from each match's own audited JSON result. Every game is
`--warmup` (never counted toward rule 52/31).

Run in three batches today while fixing harness issues along the way (a
`receive_final_reveal` connection-timing race, found and fixed —
`interop/cop_turn_sender.py`; an unhandled subprocess timeout that used
to crash the whole batch, found and fixed — the harness now saves after
every single game and retries transient failures). Numbers below are
**aggregated across all three batches**, since any one batch's win rate
swung noticeably between batches for the same configuration — a single
batch of 3-6 games isn't a reliable enough sample on its own (see
"What this doesn't mean" below).

## Result (aggregated across 37 real games total)

| Configuration | wins / valid games | win rate |
|---|---|---|
| shipped_defaults | 16/16 | **1.00** |
| **no_mobility_signal** | **11/14** | **0.79** |
| higher_expected_distance | 17/17 | **1.00** |
| no_scent_signal | 7/7 | **1.00** |

`no_mobility_signal` is the only configuration with *any* real losses
today — 3 losses across 14 real games, all lost by capture (score 5-20).
Every other configuration went undefeated across every batch.

This lines up with, but is a smaller effect than, the earlier *simulated*
ablation study's finding that mobility mattered a lot (`docs/
HEURISTIC_ABLATION.md`) — except that study found removing mobility
*helped* against its simulated barrier-placing Cop, the opposite
direction from what real matches show here. Concrete, real evidence that
the simulated and real signals can disagree, not just a theoretical risk.

## What this doesn't mean

- **Not enough games yet to fully trust the exact numbers.** The same
  `no_mobility_signal` configuration scored 50%, then 75%, then 100%
  across the three individual batches run today — real variance, not a
  bug (partly the real RL Cop's own behavior, partly this session's own
  earlier fix that made `ThiefBrain`'s move-tie-breaking genuinely random
  instead of deterministic, per your own request). 14 games is enough to
  notice a real difference exists, not enough to pin down its exact size.
- **`higher_expected_distance` (2.0) winning 17/17 here does not reverse
  its rejection in `WEIGHT_TUNING_EXPERIMENT.md`.** That rejection was
  based on a deterministic, mechanism-level test-suite failure (the exact
  corner-camping pattern from the 2026-08-12 regression), which is
  independent of how any particular batch of real games against this one
  opponent happens to turn out. Winning every game against one specific
  real opponent's current policy isn't proof the underlying risk is gone.
- **No weights have been changed in `fleeing_brain.py`.** This is a
  measurement, same as the earlier experiments — `mobility_weight`
  staying nonzero is the one finding here worth taking seriously before
  ever touching it.

## Raw data

Full per-game results (including every error/retry): `docs/
real_match_results.json`.
