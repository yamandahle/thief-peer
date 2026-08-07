# TODO — Stage 4: Language + Scent Integration

See `PRD_4_language_scent.md` for full rationale. Book: Ch.4/6.
PRD milestone: "Scent map updates turn-by-turn; hint emitted every step (true or lie)."

- [x] `domain/scent.py`: `ScentField.advance(mover_cell)` — one atomic
      decay-then-add step over the fixed Figure-4 5x5 kernel (rho=0.10),
      `absorb()` (overwrite, not merge — see `PRD_4` §4)
- [x] `domain/belief.py`: `BeliefGrid` uniform init, `observe_scent()`,
      `diffuse()`, `most_likely()`
- [x] `domain/belief.py`: add `as_matrix()` (full distribution) alongside
      `most_likely()` — required by `PRD_3`'s `_expected_distance`/
      `_lookahead_score`, which need more than the single peak cell
      (see `PRD_4` §2.4)
- [x] Rewire `peer/turn_handler.py` to a real `BeliefGrid` (diffuse then
      observe_scent each turn) instead of Stage-3's `ScriptedBelief` —
      `ThiefBrain._pick_move` itself needed no change, it already consumed
      `belief.as_matrix()`/`most_likely()` via duck typing since Stage 3
- [x] `strategy/talk_providers.py`: template provider (0 tokens), truth/lie
      verdict, `hint_max_words` cap enforced
- [x] `strategy/trash_talk.py`: provider selection + `every_n_steps`
      throttling + hard fallback to template on timeout/error
- [x] `strategy/trash_talk.py`: deceptive-verdict bias reusing
      `_expected_distance` (`PRD_4` §2.6) — not a duplicated computation
- [x] `infra/llm_provider.py`: common interface; `ollama` implemented;
      `claude_api`/`claude_cli` interface-only, raise `ProviderError`
      pointing at Stage 7's Gatekeeper (`PRD_4` §4)
- [x] Tests: scent decay formula matches the fixed spec constants exactly;
      belief diffusion conserves total probability mass; hint word-cap
      enforced; LLM timeout never stalls the move (real bounded wait, not
      just a hope); lie-detection worked example reproduced (`PRD_4` §5)

**Done when:** two live localhost peers exchange real scent fields + NL hints
every turn; the Thief's belief heatmap visibly tracks the (scripted) Cop's
scent trail; the move path still never calls an LLM.

**Milestone met:** ✅ `tests/integration/test_scent_hint_exchange.py` — real
MCP round trip carries a scent snapshot + NL hint every turn; belief tracking
is proven against a diffuse-only control (informed run lands measurably
closer to the true position); the move path never touches an LLM
(`TrashTalk(llm_provider=None)`, and `ThiefBrain`'s move methods structurally
accept no such parameter at all). 118 unit+integration tests pass, 97.4%
coverage, ruff clean, all files under 150 lines.

**Found during implementation (see `PRD_4` "Open items"):** `observe_scent()`
reweights against each turn's cumulative snapshot, not an incremental delta
— tracking is clean for ~3 consecutive turns, then early reinforcement can
compound and outweigh where the opponent has since moved to. Not a numbered
acceptance criterion here; documented as a known limit to revisit if a later
stage's longer-match testing exposes it as a real problem.

**Status:** done
