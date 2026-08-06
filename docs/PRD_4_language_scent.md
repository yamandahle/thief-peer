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

### 2.1 Scent emission & decay (book Ch.4.3, exact formula — mandatory, constant)

```
τij(t+1) = max(0, (1−ρ)·τij(t) + Δτij)
```

- `τij(t)`: current scent intensity at cell `(i,j)`, range `[0, 0.9]`.
- `ρ` (decay rate) = **0.10** — status: **constant** (Appendix ו). Deliberately
  slow: retains ~90% per full turn, so the field is a short *replay* of
  recent movement, not a single snapshot (book Ch.4.4).
- `Δτij`: new emission this turn — **0.9** at the mover's own cell (status:
  **constant**), falling off *radially* within a **5×5** field (status:
  **constant**), 0 beyond that radius.
- `max(0, ·)`: clamps to zero — intensity is never negative.

All three numeric constants (`0.9`, `0.10`, `5×5`) are **constant**-status
per the Mandatory Parameters Table — zero flexibility, not even by mutual
agreement between teams. They must be read from the shared `game.json`
(`pheromone_center_intensity`, `pheromone_decay`, `pheromone_grid_size`),
never hardcoded, even though their values happen to be fixed.

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
| `deposit(center, intensity)` | mover's cell, `0.9` | — | radial emission per §2.1 formula within the 5×5 field, merged into the field by **max**, not overwrite (a cell touched by two turns' radii keeps the stronger reading) |
| `decay_all()` | — | — | applies `(1-ρ)` to every cell, clamped to zero — called once per full turn (both sides moved) |
| `absorb(cells)` | received `{"r,c": intensity}` from opponent | — | merges into the locally-tracked field for the *opponent's* scent, max-merge as above |
| `snapshot()` | — | `{"r,c": intensity}` (sparse, zero entries omitted) | for the outgoing `TurnMessage` |

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

- **Why max-merge, not overwrite, for scent deposits/absorption:** a cell
  can legitimately receive contributions from two different recent turns'
  emission radii; taking the max preserves the strongest (most recent-ish)
  signal without an explicit timestamp per cell, keeping the field a single
  flat structure rather than a time-indexed one.
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

- [ ] `ScentField.deposit` at a center cell produces exactly the radial
      falloff values from the book's worked figure (Ch.4.3) for a 5×5 field
      centered at 0.9 — hand-verified against the book's own numeric example.
- [ ] `decay_all()` applied `n` times to a single deposit matches
      `0.9 * (1-0.10)^n` at the center cell, within floating-point tolerance.
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
