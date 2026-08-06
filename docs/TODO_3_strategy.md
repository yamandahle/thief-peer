# TODO — Stage 3: First "Blind" Pure-Python Strategy Module

See `PRD_3_strategy.md` for full rationale. Book: Ch.6.
PRD milestone: "Thief computes a legal move toward a target with no manual intervention."

- [ ] `strategy/brain_base.py`: `BrainBase`, `Decision` dataclass,
      `_pick_move`/`_decide_move` override points
- [ ] `strategy/fleeing_brain.py`: `ThiefBrain` picks the legal move maximizing
      Manhattan distance from a hardcoded/dummy target (real belief comes in Stage 4)
- [ ] `strategy/fleeing_brain.py`: implement the 4-part custom scoring
      (`_mobility_score`, `_expected_distance`, `_lookahead_score`, trail-
      unpredictability tie-break) per `PRD_3` §2.3 — not just naive
      distance-maximization
- [ ] `strategy/brain_base.py`: `resolve_brain(config, llm, rng)` dotted-path
      factory + default fallback + malformed-selector fail-fast test
- [ ] `peer/turn_handler.py` (v0): apply a scripted incoming "cop position"
      feed, single-process self-play
- [ ] Wire `ThiefBrain` into the Stage-2 MCP loop for a toy two-localhost-peer
      match against a dummy opposing feed
- [ ] Unit test proving `ThiefBrain` beats a naive "always move away on one
      axis only" baseline (average distance after N turns)
- [ ] Corner-avoidance test and bimodal-belief test (`PRD_3` §5)

**Done when:** every turn a legal move is chosen by pure Python (never LLM)
that is measurably better at evading a given point than a naive greedy
baseline, proven by a unit test.

**Status:** not started
