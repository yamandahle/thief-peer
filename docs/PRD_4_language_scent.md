# PRD — Stage 4: Language + Scent Integration

**Status:** DRAFT — pending approval before implementation
**Stage:** 4 of 7 (see `TODO.md`)
**Book reference:** Chapter 4 — "Dynamic Pheromone Trails and Collective
Memory of the Swarm"; Chapter 6 §6.4–6.5 — "Distance Heuristics and Belief
Heatmap" / "LLM Integration for Prompt Engineering"
**Modules covered:** `domain/scent.py`, `domain/belief.py`,
`strategy/talk_providers.py`, `strategy/trash_talk.py`, `infra/llm_provider.py`

---

## 1. Purpose & Theoretical Background

This stage replaces Stage 3's scripted dummy target with the real mechanism
that solves the partial-observability problem from Ch.1's Dec-POMDP framing:
**stigmergy** — indirect coordination through environment change, not direct
messages (Ch.4.2). Every mover passively leaves a scent trail; nobody reads
their *own* scent (zero informational value — you already know where you
are with certainty); each peer reads only the *opponent's* leaked scent and
builds a probability belief from it (Ch.4, "Q&A clarification" already
captured in the notes file).

The second half of this stage is the verbal layer (Ch.6.5): natural-language
hints, which may lie, generated either from a zero-token template or (opt-in)
a real LLM. This is the **only** place an LLM is permitted to touch the
system — never the move (already enforced architecturally since Stage 3,
`PLAN.md` ADR-1).

---

## 2. Detailed Description

### 2.1 Scent emission & decay (book Ch.4.3, exact formula + Figure 4 kernel — mandatory, constant)

```
τij(t+1) = max(0, (1−ρ)·τij(t) + Δτij)
```

- `τij(t)`: current scent intensity at cell `(i,j)`, range `[0, 0.9]`.
- `ρ` (decay rate) = **0.10** — status: **constant** (Appendix ו). Deliberately
  slow: retains ~90% per full turn, so the field is a short *replay* of
  recent movement, not a single snapshot (book Ch.4.4).
- `Δτij`: new emission this turn, a **fixed 5×5 radial kernel** centered on
  the mover's own cell (book Ch.4.3, Figure 4 — reproduced exactly, not
  approximated):

  | | -2 | -1 | 0 | +1 | +2 |
  |---|---|---|---|---|---|
  | **-2** | 0.04 | 0.14 | 0.20 | 0.14 | 0.04 |
  | **-1** | 0.14 | 0.42 | 0.62 | 0.42 | 0.14 |
  | **0**  | 0.20 | 0.62 | 0.90 | 0.62 | 0.20 |
  | **+1** | 0.14 | 0.42 | 0.62 | 0.42 | 0.14 |
  | **+2** | 0.04 | 0.14 | 0.20 | 0.14 | 0.04 |

  0 beyond that radius. Every cell in this table is **constant**-status —
  not just the center (0.9) and the radius (5×5) as an earlier draft of this
  PRD implied.
- `max(0, ·)`: clamps to zero — intensity is never negative.
- **Composition is additive, in one atomic per-turn step** — decay the whole
  field by `(1−ρ)`, *then add* this turn's fresh kernel deposit, exactly as
  the formula reads left to right. This is **not** a max-merge: a cell that
  already holds decayed history from two turns ago and now also falls under
  this turn's fresh kernel gets `(1−ρ)·history + kernel_value`, not
  `max(history, kernel_value)`. `ScentField` therefore exposes one method,
  `advance(mover_cell)`, that performs decay-then-add as a single step —
  never two separate `deposit()`/`decay_all()` calls a caller could invoke
  out of order or skip (see §4 for why the earlier max-merge design was
  wrong and how this was caught).

All kernel values, `ρ` (0.10), and the 5×5 radius are **constant**-status
per the Mandatory Parameters Table — zero flexibility, not even by mutual
agreement between teams. The three headline numbers (`0.9`, `0.10`, `5×5`)
must be read from the shared `game.json` (`pheromone_center_intensity`,
`pheromone_decay`, `pheromone_grid_size`); the kernel's *relative shape* is
stored as a fixed constant in `domain/scent.py` and scaled by
`pheromone_center_intensity` at construction (so a config-driven center
intensity still produces a config-driven kernel, never a hardcoded 0.9,
even though the illustrative figure and our config agree on that value).

### 2.2 What crosses the wire (ties to `PLAN.md` ADR-8)
Only the **scent field snapshot** (`{"r,c": intensity}`, sparse — zero
entries omitted) and the **hint text** are transmitted in `TurnMessage`
(`PLAN.md` §5). The Thief's true position never appears on the wire, in a
log, or in the GUI — this stage doesn't change that guarantee, it only adds
the two fields that legitimately do cross.

### 2.3 Belief update (book Ch.6.4) — and cross-checking hints against scent
Each side builds a **belief map**: a probability grid over the board for
where the opponent is, updated from the opponent's received scent field
*and* their hint (Ch.6.4's worked example, already in the notes: a hint
claiming "moved north" against a scent field reading `τ=0.00` to the north
is not just a mismatch, it's a *hole* — scent is unfakeable physical
evidence, a verbal claim is a hypothesis to be tested against it, never
trusted standalone). Concretely: `observe_scent()` updates the distribution
from the scent field alone (scent cannot lie); the hint is *not* blindly
folded into the probability update as a second independent observation —
its main role is providing the Cop's self-declared `verdict` (truth/lie) for
audit purposes (Ch.5), while our own belief stays anchored to the
unfakeable scent signal.

### 2.4 ⚠️ Design continuity check against `PRD_3_strategy.md`
`TODO.md`'s Stage 4 task list says "rewire `ThiefBrain._pick_move` to use
`belief.most_likely()`" — but `PRD_3_strategy.md` §2.3's `_expected_distance`
and `_lookahead_score` helpers need the **full probability distribution**,
not just the single peak cell (that's precisely the weakness they're
designed to fix). **Resolution**: `BeliefGrid` must expose both
`most_likely()` (kept, cheap, used by the naive-baseline comparison test in
`PRD_3`'s acceptance criteria) **and** `as_matrix()` / iteration over
`(cell, probability)` pairs (added here, required by our actual strategy).
This PRD updates that requirement explicitly so Stage 4 doesn't silently
under-deliver what Stage 3 already committed to.

### 2.5 The verbal layer (book Ch.6.5) — LLM strictly opt-in, banter only
Four supported modes (book Table 21, Appendix ו), selected via the private
`[trash_talk] provider` key — **never** the shared `game.json`:

| `provider` | Cost | Notes |
|---|---|---|
| `template` (default) | 0 tokens | canned lines, no network — the book's recommended path |
| `ollama` | free, local | via a local Ollama server |
| `claude_api` | real cost | small cloud model (e.g. Haiku), budget-capped |
| `claude_cli` | highest cost | via `claude -p`, subscription-based |

`every_n_steps` throttles LLM calls to every Nth turn (template fills the
rest). **Any LLM error or missed deadline falls back to the template** — the
banter must never stall or fail the game (book explicitly requires this
resilience). Per our earlier project decision (see `notes/`), we are setting
a **real LLM provider**, not `template`, as our actual configuration — this
stage builds the plumbing that makes either choice a one-line config change.

Hints are capped at `[hint_max_words]` (status: **negotiable**, example 15)
— enforced identically whether the source is the template or an LLM (the
LLM's system prompt states the cap too, but the code enforces it
post-generation regardless, since an LLM cannot be trusted to self-limit).
If `[map_area]` (status: **negotiable**, e.g. `"New York"`) is set, hints
should reference real landmarks from that area; unset defaults to generic
phrasing.

### 2.6 Deceptive hint strategy (carried over from `PRD_3`'s "open item")
The `verdict` (truth/lie) is a strategic choice, not random: lying has more
defensive value when the opponent's belief is *already* close to accurate
(muddying an accurate guess is worth more than muddying a wrong one), and
truth costs little when the opponent's belief is already far off. Concretely,
`ThiefBrain` (via a small decision function in `trash_talk.py`'s caller,
not the LLM) biases the truth/lie choice using the same `_expected_distance`
belief-quality signal already computed for movement in Stage 3 — reusing
the computation rather than duplicating it.

---

## 3. Requirements (Input / Output / Behavior)

### `domain/scent.py` — class `ScentField`
| Method | Input | Output | Behavior |
|---|---|---|---|
| `advance(mover_cell)` | mover's own cell | — | **one atomic step** per §2.1: decay every cell by `(1-ρ)`, then add the fixed 5×5 kernel (Figure 4) centered on `mover_cell`, clamp to zero. Replaces the earlier separate `deposit()`/`decay_all()` pair (see §4) — called once per full turn, for this peer's own trail only |
| `absorb(cells)` | received `{"r,c": intensity}` from opponent | — | **overwrites** (not merges) the locally-held snapshot of the *opponent's* scent with whatever they just sent — we don't independently simulate their trail, we only ever hold their latest self-reported snapshot |
| `snapshot()` | — | `{"r,c": intensity}` (sparse, zero entries omitted) | for the outgoing `TurnMessage`, from `advance()`'s own field |

### `domain/belief.py` — class `BeliefGrid`
| Method | Input | Output | Behavior |
|---|---|---|---|
| `__init__(board_size)` | — | — | uniform distribution over all cells |
| `observe_scent(cells)` | opponent's scent snapshot | — | Bayesian-style update scaling probability by scent intensity (book's `1 + trust*intensity` style weighting), then normalizes |
| `diffuse()` | — | — | spreads probability mass to each cell's legal-move neighborhood (one opponent move happened), then normalizes — models "the opponent moved somewhere, I don't know where" |
| `most_likely()` | — | `(int,int)` | argmax cell — kept for the Stage-3 naive-baseline comparison test only |
| `as_matrix()` | — | `list[list[float]]` | **new in this stage** — full distribution, required by `PRD_3`'s `_expected_distance`/`_lookahead_score` (see §2.4) |

### `strategy/talk_providers.py`
| Item | Behavior |
|---|---|
| `TemplateProvider` | picks a canned line from a small phrase bank, optionally referencing `[map_area]` landmarks if set; zero tokens, zero latency |
| word-cap enforcement | a single shared helper truncates/rejects any hint (template or LLM) exceeding `hint_max_words`, applied uniformly regardless of source |

### `strategy/trash_talk.py`
| Item | Behavior |
|---|---|
| provider selection | reads `[trash_talk] provider` from private TOML; unset defaults to `template` |
| `every_n_steps` throttle | calls the configured provider only on matching turns, template otherwise |
| fallback | any exception or deadline miss from the LLM path falls back to `TemplateProvider` — never propagates an error that could stall the turn |
| verdict bias | consumes the same belief-quality signal `_expected_distance` already computes (§2.6), does not duplicate that math |

### `infra/llm_provider.py`
| Item | Behavior |
|---|---|
| one common interface | `ollama` / `claude_api` / `claude_cli` adapters behind a single call signature, so `trash_talk.py` doesn't branch on provider type |
| routed through Gatekeeper | actual network calls happen only via `shared/gatekeeper.py` (Stage 7) — this stage builds the adapters, Stage 7 wires the rate-limiting doorway; until then, calls are direct but structurally isolated behind the one interface so wiring the Gatekeeper later is a one-line change, not a refactor |

---

## 4. Limitations, Constraints, Alternatives Considered

- **Why `advance()` is one atomic method, not separate `deposit()`/
  `decay_all()` calls (corrected from an earlier draft of this PRD):** the
  original design merged fresh deposits into the field by `max()`, reasoning
  that a cell could "legitimately receive contributions from two different
  recent turns' radii." That's not what the book's formula does — Ch.4.3's
  `τ(t+1) = max(0, (1−ρ)·τ(t) + Δτ)` is additive, and rule 23 is **[FATAL]**
  specifically on a decay-formula deviation. Two separate methods also let a
  caller invoke `deposit()` twice without `decay_all()` in between, or the
  reverse order, silently drifting from the formula in a way a single
  `advance(mover_cell)` call can't. Caught by directly re-reading Ch.4.3 and
  Figure 4 rather than trusting an earlier paraphrase of the formula.
- **Why `absorb()` overwrites rather than max-merges the opponent's snapshot:**
  the received `{"r,c": intensity}` already *is* the opponent's own
  `advance()`-computed cumulative field for that turn — it already reflects
  their own decay+kernel history, not a single fresh point deposit. Merging
  it against our stale, previous copy via `max()` would keep an outdated
  reading anywhere their trail has genuinely decayed since their last
  message; overwriting keeps us honest to what they just told us.
- **Why `observe_scent` doesn't fold the hint in as a second Bayesian
  observation:** the book is explicit that scent is unfakeable ground truth
  and a hint is "a claim to be tested against it, never trusted standalone"
  (Ch.4.4/6.4). Treating both as independent, equally-weighted evidence
  would let a convincingly-worded lie skew the belief update directly — the
  hint's real value is as an *audited* declaration (Ch.5's truth/lie
  verdict), not as a probability input.
- **Why the word-cap is enforced in code, not just via the LLM's system
  prompt:** an LLM cannot be trusted to self-limit reliably (the same
  hallucination-risk reasoning as ADR-1) — the cap must be a deterministic
  post-generation check, applied identically to the free template path so
  there's exactly one code path to test, not two.
- **Alternative considered and rejected: give the LLM the full belief matrix
  in its prompt for "smarter" banter.** Rejected — the LLM's role is strictly
  text generation/psychological framing (book Ch.6.5), and handing it
  structured game-state data beyond what a human bluffer would plausibly
  reason about risks it *implicitly* influencing move-adjacent decisions
  through its phrasing choices being fed back into `verdict` logic. Keeping
  the LLM's input to "your role, the opponent's last hint, the map area, the
  word cap" (already in `PLAN.md`'s reference design) keeps the LLM boundary
  clean and matches the book's own prompt shape.
- **Alternative considered and rejected: let `every_n_steps` be `1` always
  (call the LLM every turn) to maximize banter quality.** Rejected as our
  default — needlessly increases token cost and latency risk with no
  strategic benefit, since move quality is entirely independent of it;
  configurable, not hardcoded, so it can be tuned per match if desired.

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] `ScentField.advance(mover_cell)` on an empty field produces exactly the
      Figure 4 kernel values (0.90/0.62/0.42/0.20/0.14/0.04) — hand-verified
      against the book's own numeric table, not just the center value.
- [ ] `advance()` called `n` times at the *same* cell, with no other calls in
      between, matches `0.9 * (1-0.10)^0 + 0.9 * sum((1-0.10)^k for k in
      range(n))`-style accumulation at the center cell (i.e. the additive
      recurrence, not a flat re-deposit) — within floating-point tolerance.
      A regression test also asserts this does **not** equal a max-merge
      result, so a future refactor can't silently reintroduce the bug this
      PRD corrected.
- [ ] `BeliefGrid.diffuse()` conserves total probability mass (`sum(matrix)
      == 1.0 ± epsilon`) before and after diffusion.
- [ ] `BeliefGrid.as_matrix()` is available and used by `ThiefBrain`'s
      `_expected_distance`/`_lookahead_score` from `PRD_3` — an integration
      test wires Stage 3's brain to Stage 4's real belief grid and confirms
      no `most_likely()`-only shortcut remains in the move path.
- [ ] Lie-detection worked example reproduced as a test: a scent field
      concentrated in one region against a hint claiming the opposite
      direction produces a belief update that favors the scent-supported
      region, not the claimed one (mirrors the book's own Ch.4.4 example).
- [ ] Hint word-cap enforced identically for `template` and a stubbed LLM
      provider returning an over-length string — both truncated/rejected the
      same way.
- [ ] LLM timeout/error test: a stubbed provider that raises or exceeds the
      deadline results in a template-sourced hint for that turn, and the
      turn completes without stalling (measured latency bounded regardless
      of provider failure).
- [ ] `every_n_steps=3` test: over 9 scripted turns, the LLM stub is invoked
      exactly 3 times, template the other 6.
- [ ] `uv run pytest tests/unit -k "scent or belief or trash_talk or
      talk_providers" --cov` ≥ 85% coverage; `uv run ruff check` clean.

**Stage 4 "Done" milestone (from `TODO.md`, unchanged here):** two live
localhost peers exchange real scent fields + NL hints every turn; the
Thief's belief heatmap visibly tracks the (scripted) Cop's scent trail; the
move path still never calls an LLM.

---

## Open items carried over
- The Stage-1 "stuck = captured" rule ambiguity (`PRD_1_base_logic.md` §4)
  remains unresolved — not touched here, must be settled before Stage 6.
- `BeliefGrid.as_matrix()` requirement (§2.4) retroactively refines
  `TODO.md`'s Stage 4 bullet "rewire `ThiefBrain._pick_move` to use
  `belief.most_likely()`" — the actual wiring must expose the full
  distribution, not just the peak; worth updating `TODO.md`'s wording to
  match when next touched, so a future reader doesn't get misled by the
  narrower original phrasing.
- **Found during integration testing, not a wiring bug — a limit of the
  book's simple reweighting update:** `observe_scent()` reweights against
  each turn's *cumulative* scent snapshot (§2.3), not an incremental delta.
  Over many consecutive turns on a short, contiguous trail, early strong
  reinforcement compounds and can outweigh evidence for where the opponent
  has since moved on to — verified empirically (informed vs. a diffuse-only
  control) tracking is clean and unambiguous for the first ~3 turns, then
  degrades. Not a numbered acceptance criterion here (none requires
  multi-turn tracking), so not fixed in this stage; worth a real fix later
  (e.g. discount the belief matrix's own accumulated weight over time, or
  reweight from the *incremental* scent delta instead of the raw cumulative
  snapshot) if match-length testing in a later stage exposes it as a real
  problem rather than a theoretical one.
