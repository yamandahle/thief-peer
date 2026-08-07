# TODO — Stage 4: Language + Scent Integration

See `PRD_4_language_scent.md` for full rationale. Book: Ch.4/6.
PRD milestone: "Scent map updates turn-by-turn; hint emitted every step (true or lie)."

- [ ] `domain/scent.py`: `ScentField.advance(mover_cell)` — one atomic
      decay-then-add step over the fixed Figure-4 5x5 kernel (rho=0.10),
      `absorb()` (overwrite, not merge — see `PRD_4` §4)
- [ ] `domain/belief.py`: `BeliefGrid` uniform init, `observe_scent()`,
      `diffuse()`, `most_likely()`
- [ ] `domain/belief.py`: add `as_matrix()` (full distribution) alongside
      `most_likely()` — required by `PRD_3`'s `_expected_distance`/
      `_lookahead_score`, which need more than the single peak cell
      (see `PRD_4` §2.4)
- [ ] Rewire `ThiefBrain._pick_move` to use `belief.as_matrix()` (full
      distribution) instead of the Stage-3 dummy target — `most_likely()`
      alone is kept only for the Stage-3 naive-baseline comparison test
- [ ] `strategy/talk_providers.py`: template provider (0 tokens), truth/lie
      verdict, `hint_max_words` cap enforced
- [ ] `strategy/trash_talk.py`: provider selection + `every_n_steps`
      throttling + hard fallback to template on timeout/error
- [ ] `strategy/trash_talk.py`: deceptive-verdict bias reusing
      `_expected_distance` (`PRD_4` §2.6) — not a duplicated computation
- [ ] `infra/llm_provider.py`: ollama / claude_api / claude_cli adapters
      behind one interface
- [ ] Tests: scent decay formula matches the fixed spec constants exactly;
      belief diffusion conserves total probability mass; hint word-cap
      enforced; LLM timeout never stalls the move; lie-detection worked
      example reproduced (`PRD_4` §5)

**Done when:** two live localhost peers exchange real scent fields + NL hints
every turn; the Thief's belief heatmap visibly tracks the (scripted) Cop's
scent trail; the move path still never calls an LLM.

**Status:** not started
