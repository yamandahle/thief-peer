# PRD — Stage 1: Base Logic (Grid, Movement, Capture/Survival Rules)

**Status:** DRAFT — pending approval before implementation
**Stage:** 1 of 7 (see `TODO.md`)
**Book reference:** Chapter 3 — "Board, Physics, Scoring"
**Modules covered:** `constants.py`, `exceptions.py`, `domain/board.py`,
`domain/own_state.py`, `domain/rules.py`

---

## 1. Purpose & Theoretical Background

This stage builds the deterministic, network-free physical model of the game:
the discrete grid, legal movement, and the rules that decide capture/survival.
It corresponds to the state space `S` and part of the action space `{Ai}` in
the Dec-POMDP formalism (book Ch.1) — the part of the "world" that is
**common knowledge by contract**, not something either peer must infer.

Critically, there is no central server enforcing these rules (book Ch.2/3): the
Thief peer computes its own transitions locally, from the same shared
`config/game.json` contract the Cop peer also loads. This stage's correctness
is what makes that possible — if this peer's board logic ever disagrees with
the Cop's about what's a legal move, the match becomes incoherent regardless
of how good the strategy or crypto layers are.

This stage deliberately excludes: networking (Stage 2), scent/belief (Stage 4),
crypto sealing (Stage 6), and reporting (Stage 7). It must be fully testable in
a single Python process with no external dependencies.

---

## 2. Detailed Description

### 2.1 Coordinate system
- Grid is `grid_size × grid_size` cells (mandatory parameter `[board size]`,
  status: **minimum**, example value 7 — read from config, never hardcoded).
- Origin corner and starting index (`axis_origin_corner`, `axis_start_index`)
  are config-driven (status: **negotiable**, defaults top-left, 0) — the Board
  class must not assume a specific corner/index, it reads both from config.
- Cells are addressed as `(row, col)` integer tuples.

### 2.2 Movement
- Legal moves: one orthogonal step — **N, S, E, W** — or **STAY**. This move
  set is **constant** (book Ch.3, Appendix ו) — no diagonal moves, ever, not
  even by mutual agreement between teams.
- A move is legal iff the destination cell is (a) within grid bounds and (b)
  not a barrier cell.
- The Thief peer **never places barriers** (Cop-only mechanic, book Ch.3) —
  but must correctly treat existing barrier cells (received via the shared
  config or, later, via the wire protocol) as impassable.

### 2.3 Barriers (read-only from the Thief's perspective)
- Barriers are permanent once placed — no un-blocking.
- Board must support querying "is `(r,c)` a barrier?" and "what are the legal
  moves from `(r,c)` given the current barrier set?"
- **Capture rule**: if a barrier is ever placed on the cell the Thief currently
  occupies, that is an **instant capture** (Appendix ה cross-check addition) —
  this stage must expose a check for this condition; the actual barrier-arrival
  event comes over the wire in Stage 2+, but the *rule* belongs here.

### 2.4 Capture / Survival rules
- **Captured** if: (a) the Cop's claimed position equals the Thief's true
  position (validated, not just claimed — see Stage 6 for the cryptographic
  proof half of this), (b) a barrier lands on the Thief's current cell, or (c)
  the Thief has **no legal move available** on its turn (Appendix ה addition —
  "stuck" counts as caught, not a forced pass).
- **Survived** if the Thief reaches `[survival threshold]` (status:
  **minimum**, example 35) moves without being captured.
- These are pure functions of `(board, own_state, config)` — no I/O, no
  network — so they're trivially unit-testable in isolation.

---

## 3. Requirements (Input / Output / Behavior)

### `constants.py`
- `Direction` enum: `N`, `S`, `E`, `W` (no diagonal members — enforce the
  constant move-set rule at the type level, not just by convention).
- `MoveType` enum: `MOVE`, `HOLD` (Thief never has `BARRIER`).
- `DELTAS: dict[Direction, tuple[int, int]]` — the `(dr, dc)` offset per direction.

### `exceptions.py`
- `ConfigError` — raised when a required config term is missing/invalid.
- `SimulationError` — raised on an internal invariant violation (e.g., asked
  to move from an already-illegal position).

### `domain/board.py` — class `Board`
| Method | Input | Output | Behavior |
|---|---|---|---|
| `__init__` | `size: int`, `barriers: set[tuple[int,int]]` | — | validates `size > 0`; stores barriers as an immutable frozenset |
| `in_bounds(cell)` | `(r,c)` | `bool` | `0 <= r < size and 0 <= c < size` |
| `is_barrier(cell)` | `(r,c)` | `bool` | membership check |
| `legal_moves(position, barriers)` | current cell, current barrier set | `list[tuple[Direction, tuple[int,int]]]` | applies `DELTAS`, filters by `in_bounds` + not-a-barrier; **always includes STAY** as a legal option |
| `distance(a, b)` | two cells | `int` | Manhattan distance `abs(a.r-b.r) + abs(a.c-b.c)` |

**Why Manhattan, not Euclidean:** matches orthogonal-only movement exactly —
it's the true minimum step count between two cells given this move set
(admissible heuristic), whereas Euclidean distance would under/over-estimate
actual reachability. (Book Ch.6 uses this same formula for belief-driven
targeting — Stage 3/4 will reuse this method, not reimplement it.)

### `domain/own_state.py` — class `OwnGameState`
| Field | Type | Meaning |
|---|---|---|
| `position` | `tuple[int,int]` | current true position (mutated only via `apply_move`) |
| `visited` | `set[tuple[int,int]]` | trail of previously-occupied cells this sub-game |
| `known_barriers` | `set[tuple[int,int]]` | barriers known to exist (grows over the match, never shrinks) |
| `step_count` | `int` | moves made so far this sub-game |

| Method | Behavior |
|---|---|
| `apply_move(direction, board)` | validates the move is in `board.legal_moves(position, known_barriers)`, raises `SimulationError` if not; updates `position`, appends old position to `visited`, increments `step_count` |
| `record_barrier(cell)` | adds `cell` to `known_barriers` (called when a barrier-placement event is learned, wired up in Stage 2+) |

### `domain/rules.py`
| Function | Input | Output | Behavior |
|---|---|---|---|
| `is_captured_by_barrier(state, new_barrier_cell)` | current state, newly-placed barrier cell | `bool` | `True` iff `new_barrier_cell == state.position` |
| `is_captured_by_stuck(state, board)` | state, board | `bool` | `True` iff `board.legal_moves(...)` returns only `STAY` and the rules treat that as caught — **note:** STAY is always technically legal per §2.2, so "stuck" here means no *movement* options (`MOVE` type) remain, not literally zero legal actions; this needs explicit unit tests to pin the exact definition against Appendix ה's wording before Stage 6 locks it into the audited log |
| `has_survived(state, survival_threshold)` | state, config value | `bool` | `state.step_count >= survival_threshold` |

---

## 4. Limitations, Constraints, Alternatives Considered

- **No diagonal movement, ever** — this is a `constant` mandatory parameter
  (Appendix ו); implementing it as an `Enum` with only 4 directional members
  (rather than a config-driven list that happens to default to 4) makes
  violating this rule a type error, not just a config mistake.
- **Immutable `Board`, mutable `OwnGameState`** — the board's barrier set is
  fixed at construction for a given sub-game snapshot (new barriers arrive as
  *new* `Board` instances or explicit `record_barrier` calls on state, kept
  separate from the geometry class) — this keeps `Board` trivially hashable/
  testable and avoids accidental aliasing bugs between "the rules of physics"
  and "what I currently know."
- **Alternative considered and rejected: encode barriers as part of `Board`
  and mutate them in place.** Rejected because it would make `Board` stateful
  in a way that couples geometry (fixed) with knowledge-over-time (growing) —
  harder to unit test and harder to reason about when barrier knowledge is
  partial vs. complete (a concern that matters once wire events start feeding
  `known_barriers` in later stages).
- **"Stuck = captured" is a genuinely ambiguous rule as literally stated** in
  the book's Appendix ה cross-check addition — since STAY is always legal, a
  literal reading would mean nobody is ever "stuck." This PRD flags the
  ambiguity explicitly (per the book's own "academic freedom" clause, page 5 —
  documented contradiction + our chosen reading) rather than silently guessing:
  **our reading is "stuck" = no legal `MOVE` (only `STAY` available)**, and this
  will be re-confirmed against Appendix ה's literal text before Stage 6 seals
  it into the audited game log, since a wrong reading here would be a
  cryptographically-provable rules violation once matches are audited.

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] `Board(size=7, barriers=set())` — a Thief at a corner has exactly 3 legal
      `MOVE` options + `STAY`; a Thief at the center has 4 + `STAY`.
- [ ] A barrier adjacent to the Thief removes exactly that one direction from
      `legal_moves`, no others.
- [ ] `distance((0,0), (3,4)) == 7` (Manhattan, not `5` which would be Euclidean-ish).
- [ ] `OwnGameState.apply_move` raises `SimulationError` on an illegal move
      (into a barrier, or off-grid) — state is unchanged after the exception.
- [ ] `visited` and `step_count` update correctly across a scripted sequence of
      5 moves; `known_barriers` only grows, never shrinks, across
      `record_barrier` calls.
- [ ] `is_captured_by_barrier` returns `True` only when the barrier lands
      exactly on the Thief's current cell — not an adjacent cell.
- [ ] `has_survived` is `False` at `step_count == survival_threshold - 1` and
      `True` at `step_count == survival_threshold`.
- [ ] All values (`grid_size`, `survival_threshold`, etc.) are read from
      `config/thief/game.json` in tests via a test fixture config — **no
      hardcoded 7s or 35s inside `board.py`/`rules.py` themselves.**
- [ ] `uv run pytest tests/unit -k "board or own_state or rules" --cov` ≥ 85%
      coverage on these three modules; `uv run ruff check` clean.

**Stage 1 "Done" milestone (from TODO.md, unchanged here):** a single Python
process builds a board + Thief state and enumerates legal N/S/E/W/STAY moves
respecting a hardcoded barrier set and capture/survival rules, fully
unit-tested — no network code exists yet.
