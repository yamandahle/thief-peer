# PRD — Stage 3: Strategy Module (Movement Decision-Making)

**Status:** DRAFT — pending approval before implementation
**Stage:** 3 of 7 (see `TODO.md`) — move logic here; real belief/scent wiring
comes in Stage 4, LLM verbal layer also in Stage 4 (this PRD covers the module's
full architecture per book Ch.6, scoped implementation follows TODO.md's split)
**Book reference:** Chapter 6 — "Strategy Module and Decision-Making"
**Modules covered:** `strategy/brain_base.py`, `strategy/fleeing_brain.py`

---

## 1. Purpose & Theoretical Background

This is the graded differentiator (`PLAN.md` ADR-1, ADR-7; `PRD.md` §3.5). The
book is explicit (Ch.6.2) that the infrastructure built in earlier stages
"knows how to move a pipeline — locking commitments, signature locking — but
does not know WHAT to decide." The decision logic must be independent and
**never delegated to the LLM**, because language models hallucinate when
reasoning over coordinates, directions, and distances in text form, and may
confidently return an illegal move (Ch.6.5). This is architecturally enforced
already at `PLAN.md` ADR-1: `BrainBase.decide()` computes the move via
`_pick_move`/`_decide_move` in pure Python *before* the hint/verdict half of
`Decision` is even touched, and the LLM (if enabled at all, Stage 4) only ever
fills in the `hint`/`verdict`/`reasoning` fields.

### 1.1 The three book-sanctioned tracks (Ch.6.3, equal-rights)
1. **Pure heuristics** (Manhattan distance + Bayesian belief) — the book's own
   default/shipped baseline.
2. **Your own custom algorithm** — richer movement policy combining belief
   maps, scent maps, barrier exploitation, forward search (e.g. minimax/
   expectimax against the opponent's believed position).
3. **Reinforcement Learning (Q-Learning)** — explicitly **one optional tool
   among three**, not something the course teaches, not required. The book
   states plainly: a winning agent can be built entirely without RL.

**Our choice: track 2, a custom algorithm built on top of the same
Manhattan+Bayesian belief foundation as track 1** (see §4 for why RL is
rejected). This satisfies the book's requirement that *some* non-trivial
algorithmic intelligence exist beyond the naive shipped baseline (per our
comparison with the lecturer's reference repo — its `ThiefBrain` is
explicitly documented as "deliberately simple," "the student's mission" to
improve).

---

## 2. Detailed Description

### 2.1 The belief-driven baseline (book Ch.6.4, shared foundation)
Both sides are fully symmetric and never see the opponent's true position.
Each side builds a **belief map** — a probability grid over the board — from
the opponent's scent field (Ch.4) and hints (may lie), updated via a
Bayesian-style rule. The book's baseline decision rule:

```
D = |x_cop − x_target| + |y_cop − y_target|          (Manhattan distance)
target = argmax_s belief(s)                           (belief-peak cell)
```

The Thief's baseline: choose the legal move that **maximizes** D from the
believed Cop location (flee from the peak). This is the book's shipped
default and our floor, not our ceiling.

### 2.2 Where our custom algorithm improves on the baseline
The naive "maximize distance from the single peak cell" policy has three
concrete weaknesses the book itself hints at (belief distributions can be
diffuse or split into two peaks after a contradicting hint, Ch.6.4's worked
example) and that are simply exploitable by any competent Cop:

1. **Corner/dead-end blindness.** Maximizing instantaneous distance can walk
   the Thief into a board corner where future mobility collapses — even
   though the distance *right now* looks good, the position is a trap one or
   two moves later.
2. **Single-peak fragility.** Targeting only `argmax belief(s)` ignores the
   rest of the distribution. When belief is diffuse or bimodal (book's own
   example: a contradicted hint splits the mass into two peaks), fleeing the
   single peak can walk the Thief *toward* the second-most-likely cell.
3. **Predictable trail.** The Thief's own movement passively emits scent
   (Ch.4) that the Cop reads directly — a Thief that always moves in a
   straight line away from the peak leaves an extrapolable trail, handing the
   Cop a nearly free prediction of the next few cells.

### 2.3 Our custom algorithm — four additions over the baseline
1. **Mobility-aware scoring** — among the legal moves that are within one
   step of the best Manhattan gain, prefer the one leaving the *most* future
   legal moves available from the destination cell (a 1-ply lookahead on
   `board.legal_moves`), not just the raw distance value. This directly
   defends against corner-trapping.
2. **Expected-distance over the full belief distribution**, not just the
   peak — score each candidate move by
   `sum(belief(s) * distance(candidate, s) for s in board)` instead of
   `distance(candidate, argmax belief)`. This is strictly more information-
   using and degrades gracefully when the distribution is diffuse or
   bimodal, exactly the case the book calls out.
3. **Trail-unpredictability tie-break** — when multiple candidate moves score
   within a small epsilon of each other, break the tie toward the
   least-recently-visited direction rather than a fixed preference, so the
   Thief doesn't telegraph a straight-line escape route through its own
   scent trail.
4. **One-ply minimax lookahead (book Ch.6.3.1's "forward search... against
   the opponent's belief")** — for each candidate move, estimate the Cop's
   best response next turn (assume the Cop greedily minimizes distance to
   the Thief's post-move position), and prefer the candidate that maximizes
   the **worst-case** resulting distance after that response, rather than
   this turn's distance alone. This is a shallow, deterministic search — not
   training, not RL — fully within the "your own algorithm" track.

None of this touches the LLM. All four additions are pure functions of
`(board, own_state, belief)`, exactly like the baseline they extend.

---

## 3. Requirements (Input / Output / Behavior)

### `strategy/brain_base.py`
| Item | Behavior |
|---|---|
| `class Decision` (dataclass) | `move_type: MoveType`, `direction: Direction \| None`, `hint: str`, `verdict: str`, `reasoning: str`, `response_seconds: float` — matches `PLAN.md` §5 exactly; Thief never produces `move_type == BARRIER` |
| `class BrainBase` | `decide(state, belief, opponent_hint, ...) -> Decision`: computes the move via `_pick_move` (pure Python, always) first, then delegates only `hint`/`verdict`/`reasoning` to the trash-talk layer (Stage 4). Never calls an LLM provider itself. |
| `_pick_move(moves, state, belief)` | abstract — subclasses implement the actual policy |
| `resolve_brain(config, llm, rng) -> BrainBase` | dotted-path factory reading `[strategy] thief_class` from the private TOML (`PLAN.md` ADR-7); defaults to `ThiefBrain` if unset; fails fast (`TypeError`) if the target doesn't subclass `BrainBase` |

### `strategy/fleeing_brain.py` — class `ThiefBrain(BrainBase)`
| Method | Input | Output | Behavior |
|---|---|---|---|
| `_pick_move(moves, state, belief)` | legal `(Direction, cell)` list, `OwnGameState`, `BeliefGrid` | chosen `(Direction, cell)` | implements the 4-part scoring in §2.3: mobility score + expected-distance score, combined by weighted sum; ties broken by least-recently-visited |
| `_mobility_score(cell, board, barriers)` | candidate cell | `int` | count of legal moves from that cell (helper, unit-testable alone) |
| `_expected_distance(cell, belief)` | candidate cell, belief grid | `float` | `sum(belief(s) * board.distance(cell, s) for s in board)` (helper, unit-testable alone) |
| `_lookahead_score(cell, belief, board)` | candidate cell | `float` | worst-case distance after simulating the Cop's best 1-ply response (helper, unit-testable alone) |

Each helper is a small, independently-testable pure function — matches the
guidelines' "building block" mandate (Input/Output/Setup clearly defined,
single responsibility) and keeps `_pick_move` itself under the 150-line cap
by composition rather than one large function.

### Stage 3 scope note (per `TODO.md`)
At Stage 3, `belief` is a **scripted dummy** (single fixed target, no real
Bayesian update yet — that's Stage 4). The scoring functions above are
written against the `BeliefGrid` *interface*, not a concrete Stage-4
implementation, so no rework is needed when Stage 4 wires in the real thing.

---

## 4. Limitations, Constraints, Alternatives Considered

- **Why not Reinforcement Learning (Q-Learning):** the book presents this as
  one optional tool among three, explicitly not taught in the course and not
  required (Ch.6.3). RL requires a training loop, an epsilon-greedy
  exploration schedule, and a Q-table sized to the state space — real
  engineering cost for a book-acknowledged non-requirement. Our 4-part
  custom algorithm (§2.3) already goes beyond the naive heuristic baseline
  the book itself distinguishes as "the student's mission" to improve,
  without that added complexity and training-time risk. **Rejected, not
  ruled out**: if time permits after Stage 7 is solid, `resolve_brain`'s
  pluggable design (`PLAN.md` ADR-7) means an RL-based `ThiefBrain` subclass
  could be added later as a drop-in replacement without touching the
  surrounding architecture — the Bellman update `Q(s,a) ← Q(s,a) +
  α[r + γ·max_a' Q(s',a') − Q(s,a)]` and epsilon-greedy action selection are
  documented in the book (Ch.6.3, code sample) if we revisit this.
- **Why not pure heuristics (track 1) as-is:** it's the book's own shipped
  baseline and the reference repo's default — using it unmodified would not
  demonstrate the "Adaptation" differentiation the grading rubric calls out
  (`PRD.md` §2.1, `PLAN.md` §6). Track 2 (custom algorithm) was chosen
  specifically because it lets us keep the same transparent, debuggable,
  deterministic character of track 1 while adding real algorithmic
  intelligence on top.
- **One-ply lookahead only, not full minimax/expectimax search:** a deeper
  search would require modeling the Cop's belief of the Thief (a second-order
  belief), which is unbounded complexity for uncertain benefit at this board
  size; one-ply against a "Cop greedily minimizes distance" assumption is a
  reasonable, cheap approximation that still beats zero-lookahead.
- **Alternative considered and rejected: encode all four scoring
  contributions as one large function.** Rejected in favor of the helper
  decomposition in §3 — keeps each contribution independently unit-testable
  and keeps `_pick_move` itself readable and under the 150-line file cap.

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] `ThiefBrain._pick_move` never returns a move outside `moves` (the
      legal-move list) — cannot select an illegal cell regardless of scoring.
- [ ] `_mobility_score`, `_expected_distance`, `_lookahead_score` each have
      dedicated unit tests with hand-computed expected values on a small
      fixed board (mirroring the book's own worked example style, Ch.6.4).
- [ ] **Baseline-beating test** (already required by `TODO.md` Stage 3):
      over a scripted N-turn simulation against a fixed/simple pursuing
      target, `ThiefBrain` achieves a strictly better average survival
      distance than a naive "always maximize distance from the single belief
      peak" baseline implementation kept in the test file for comparison.
- [ ] **Corner-avoidance test**: construct a board state where the naive
      baseline's top-distance move leads into a corner with only 1 legal
      exit next turn, and assert `ThiefBrain` prefers a different candidate
      with higher `_mobility_score` instead.
- [ ] **Bimodal-belief test**: construct a belief grid with two separated
      probability peaks and assert `ThiefBrain`'s `_expected_distance`
      scoring (not single-peak targeting) produces a different — and
      provably better, by total expected distance — move than naive
      argmax-targeting would.
- [ ] **LLM-never-called test**: assert `_pick_move` and its three helpers
      never accept or invoke an LLM/provider object — enforced by not
      passing one into their signatures at all (a structural guarantee, not
      just a runtime check).
- [ ] `resolve_brain` unit tests: default fallback to `ThiefBrain` when
      `[strategy]` unset; fails fast with a clear error on a malformed or
      non-`BrainBase` dotted path.
- [ ] `uv run pytest tests/unit -k "brain or fleeing" --cov` ≥ 85% coverage
      on these modules; `uv run ruff check` clean.

**Stage 3 "Done" milestone (from `TODO.md`, unchanged here):** every turn a
legal move is chosen by pure Python (never LLM) that is measurably better at
evading a given point than a naive greedy baseline, proven by a unit test.

---

## Open items carried over
- The Stage-1 "stuck = captured" rule ambiguity (see `PRD_1_base_logic.md`
  §4) remains unresolved — not touched by this stage, must be settled before
  Stage 6.
- The deceptive-hint/verdict correlation idea (lie more convincingly when
  the belief peak is already accurate, tell the truth when it costs little)
  is a natural extension of this strategy's spirit but belongs to Stage 4's
  `trash_talk.py` scope (book Ch.6.5's verbal layer), not this stage's move
  logic — noted here so it isn't forgotten when `PRD_4_language_scent.md` is
  drafted.
