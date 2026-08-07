# TODO — Stage 3: First "Blind" Pure-Python Strategy Module

See `PRD_3_strategy.md` for full rationale. Book: Ch.6.
PRD milestone: "Thief computes a legal move toward a target with no manual intervention."

- [x] `strategy/brain_base.py`: `BrainBase`, `Decision` dataclass,
      `_pick_move`/`_decide_move` override points
- [x] `strategy/fleeing_brain.py`: `ThiefBrain` picks the legal move maximizing
      Manhattan distance from a hardcoded/dummy target (real belief comes in Stage 4)
- [x] `strategy/fleeing_brain.py`: implement the 4-part custom scoring
      (`_mobility_score`, `_expected_distance`, `_lookahead_score`, trail-
      unpredictability tie-break) per `PRD_3` §2.3 — not just naive
      distance-maximization
- [x] `strategy/brain_base.py`: `resolve_brain(config, llm, rng)` dotted-path
      factory + default fallback + malformed-selector fail-fast test
- [x] `peer/turn_handler.py` (v0): apply a scripted incoming "cop position"
      feed, single-process self-play
- [x] Wire `ThiefBrain` into the Stage-2 MCP loop for a toy two-localhost-peer
      match against a dummy opposing feed
- [x] Unit test proving `ThiefBrain` beats a naive "always move away on one
      axis only" baseline (average distance after N turns)
- [x] Corner-avoidance test and bimodal-belief test (`PRD_3` §5)

**Done when:** every turn a legal move is chosen by pure Python (never LLM)
that is measurably better at evading a given point than a naive greedy
baseline, proven by a unit test.

**Milestone met:** ✅ `test_beats_naive_single_peak_baseline_over_a_scripted_chase`
(`tests/unit/test_fleeing_brain.py`) walls off a one-wide dead-end pocket
that the naive single-peak-fleeing baseline walks straight into (average
survival distance collapses to 1.70); `ThiefBrain`'s mobility+lookahead-aware
scoring routes around it (5.13 average) — over 3x better. Corner-avoidance
and bimodal-belief tests pass independently. `_pick_move`/its three helpers
have no `llm`/`provider` parameter at all (structural, not just runtime,
guarantee). 76 unit+integration tests pass, 98.59% coverage, ruff clean.

**Doc corrections made during implementation (see `PRD_3_strategy.md`):**
`_pick_move` and `_expected_distance`'s signatures were missing a `board`
parameter their own described bodies needed (`board.legal_moves`/
`board.distance`) — added and noted inline in the PRD.

**Status:** done
