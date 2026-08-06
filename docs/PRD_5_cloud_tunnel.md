# PRD — Stage 5: Public URL + Tunnel Reachability

**Status:** DRAFT — pending approval before implementation
**Stage:** 5 of 7 (see `TODO.md`)
**Book reference:** Chapter 2 §2.4/2.4.1 — "Tunneling and Environment
Separation"; cross-referenced to Chapter 8 §8.4 — "Reliability Patterns:
Deadline Tracker and Watchdog"
**Modules covered:** `infra/mcp_client.py` (extended), `shared/watchdog.py`
(**new module — see §2.3, a `PLAN.md` addendum**), private TOML config

---

## 1. Purpose & Theoretical Background

Stages 1–4 proved the topology and content work over `localhost`. This stage
replaces that shortcut with what the book actually requires for league play
(Ch.9): each peer's FastMCP server exposed to the **public internet** via a
tunnel (ngrok/Localtonet named explicitly), since most machines sit behind
NAT and are not directly reachable (Ch.2.4.1). This is not a convenience
upgrade — it's the difference between "two students on the same laptop" and
"two students over the internet," which is literally the scenario the whole
architecture is designed for.

🎯 The book explicitly cross-references this section to Ch.8's reliability
patterns: *"tunnel stability is part of the game's reliability requirement,
ties to Watchdog/Deadline Tracker."* The book's own worked "what if" analysis
(Ch.2.4.1, Figure 2 discussion) is blunt about the failure mode: **if either
side's tunnel drops, the opposing side loses the ability to complete a move
and reaches a "closed mailbox" during turn timing — a direct path to
deadlock**, since there is no central judge to notice and intervene. This
stage's job is proving *reachability*; detecting and recovering from a
*dead* connection is this PRD's second half.

---

## 2. Detailed Description

### 2.1 NAT traversal, in one sentence
A tunnel tool binds a public URL that performs NAT traversal (STUN-family
protocols) so a rival anywhere in the world can reach this peer's local
FastMCP server through that public address — no port-forwarding or static IP
setup required on our end.

### 2.2 Config split applies here too (`PLAN.md` ADR-5)
The tunnel's public URL and the opponent's URL are both **private, local-only**
settings — they describe *this* peer's network reachability and *this*
match's counterpart address, not a term both sides must cryptographically
agree on. They belong in `config/thief/game.toml`, never in the shared,
signed `game.json`.

### 2.3 🎯 New module: `shared/watchdog.py` (addendum to `PLAN.md` §1)
`PLAN.md`'s original module layout did not list a dedicated Watchdog module —
this PRD adds one, since the book explicitly ties tunnel reliability to it
right here (Ch.2.4.1's cross-reference to Ch.8.4.2). Two **distinct**
reliability concerns, per the book's own separation:

- **Deadline Tracker** (per-request): every outbound MCP call gets a
  timestamp + expiry; a missed deadline is retried with backoff or resolved
  to `TECHNICAL_LOSS` via the turn FSM (`PLAN.md` ADR-2) — this is
  `mcp_client.py`'s job, §2.4 below.
- **Watchdog** (whole-system): an independent background check verifying
  the main loop is still alive at all — a frozen main loop (e.g. blocked on
  a hung socket call that isn't timing out correctly) would never trip its
  *own* deadline tracker, since the code that would raise the timeout is
  itself what's frozen. The Watchdog is a second, independent observer for
  exactly this failure mode: `persist_state()` + `controlled_shutdown()`
  when the heartbeat goes stale, rather than a silent, unrecoverable hang.

### 2.4 Connect-with-retry/backoff (Deadline Tracker applied to `mcp_client.py`)
`McpTransport.call()` (introduced minimally in Stage 2) gets real resilience
here: retry with exponential backoff against a non-localhost `opponent_url`,
bounded by `network.response_timeout_sec` (status: **negotiable**, example
30s per the Params Table) — all timing values from config, never hardcoded,
per the standing "no magic values" rule.

---

## 3. Requirements (Input / Output / Behavior)

### `config/thief/game.toml` (private, extended)
| Key | Behavior |
|---|---|
| `network.public_url` | this peer's own tunnel-assigned public URL (operator sets it after starting the tunnel tool; not auto-detected — keeps this stage's scope to consuming the URL, not launching the tunnel process itself) |
| `network.opponent_url` | now expected to be the **opponent's public URL**, not a `localhost` address (Stage 2's value was localhost-only) |
| `network.retry_backoff_sec` / `network.max_retries` | reuse the same shape as the Gatekeeper's rate-limiter fields (`PLAN.md` §5) for consistency, even though this is a connection retry, not an API rate limit |

### `infra/mcp_client.py` (extended)
| Method | Behavior |
|---|---|
| `call(tool_name, payload)` | now wraps the Stage-2 call in retry-with-backoff: on connection failure, wait `retry_backoff_sec * (attempt)` (simple linear backoff, see §4 for why not exponential) up to `max_retries`, then raise a typed, **operator-facing** error naming the unreachable URL and the number of attempts made — never a bare socket traceback |
| deadline enforcement | the overall call (including retries) is bounded by `response_timeout_sec`; exceeding it raises a distinct `DeadlineExceededError`, letting the turn FSM (`PLAN.md` ADR-2) resolve to `TECHNICAL_LOSS` cleanly rather than hanging indefinitely |

### `shared/watchdog.py` (new)
| Function | Input | Output | Behavior |
|---|---|---|---|
| `watchdog_check(last_heartbeat, timeout_sec)` | last heartbeat timestamp, threshold (config, example 60s per Params Table `watchdog_timeout_sec`) | `"ALIVE"` \| `"SHUTDOWN"` | if `now - last_heartbeat > timeout_sec`: calls `persist_state()` then `controlled_shutdown()`, returns `"SHUTDOWN"`; otherwise `"ALIVE"` — matches the book's own reference sketch (Ch.8.4.2) closely, since this is a well-specified, low-risk pattern worth implementing close to the book's exact shape |
| `persist_state()` | current match state | — | writes enough state to disk that a future run could diagnose (not necessarily resume) what the match was doing when it froze — ties into Stage 7's logging, kept minimal here |
| `controlled_shutdown()` | — | — | releases the MCP server/client cleanly, closes any open log handles — never a bare process kill |
| heartbeat producer | the main peer loop (`peer/runtime.py`, arriving fully in later stages) updates a shared timestamp each turn cycle; this stage builds the *checker*, wiring the *producer* into the real turn loop happens as `PeerRuntime` is completed |

---

## 4. Limitations, Constraints, Alternatives Considered

- **Why a tunnel and not a static IP / manual port-forwarding:** the book
  names ngrok/Localtonet explicitly (Ch.2.4) precisely because most students'
  machines sit behind NAT/firewalls they don't control (dorms, shared
  networks, university Wi-Fi) — a tunnel is the only reachability option
  that doesn't require router-admin access, which not every student has.
- **Why linear backoff, not exponential:** with `max_retries` small (Params
  Table default 3) and `retry_backoff_sec` small (default 5s), the
  difference between linear and exponential backoff is a few seconds over
  the whole retry window — exponential backoff's real value (protecting a
  server from thundering-herd retries) doesn't apply here, since this is a
  1:1 connection to a single known opponent, not a shared service under
  load. Linear keeps the operator-facing wait time predictable.
- **Why the Watchdog is a separate module from the Deadline Tracker, not
  folded together:** the book's own text treats them as two named,
  distinct patterns (Ch.8.4.1 vs 8.4.2) solving different failure classes —
  a per-request timeout that fires correctly *cannot* by itself detect the
  case where the code that would fire it is itself hung. Merging them would
  quietly drop the whole-system-freeze protection the book calls for.
- **Why this stage doesn't launch the tunnel process itself
  (e.g. shelling out to `ngrok start`):** keeps this stage's scope to
  *consuming* a tunnel URL the operator has already started, matching the
  book's own framing (Ch.2.4: "each group must expose its server... via a
  tool such as ngrok") as an operator action, not something the peer process
  automates — automating tunnel lifecycle management is real scope the book
  doesn't ask for and would add a subprocess-management surface for no
  required benefit.
- **Alternative considered and rejected: skip the Watchdog entirely and rely
  only on the Deadline Tracker.** Rejected — this is exactly the gap the
  book calls out by name, and "Architecture" is one of the four graded
  success metrics (`PRD.md` §2.1); omitting a book-named, explicitly
  cross-referenced reliability pattern here would be a visible, avoidable
  gap in a grader's checklist pass.

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] Manual/integration run: this Thief peer completes a full scripted
      match against a second independent process reachable **only** through
      a public tunnel URL — no localhost shortcut, matching the "two
      students over the internet" scenario (book's own framing).
- [ ] `McpTransport.call()` against an unreachable public URL retries exactly
      `max_retries` times with the configured backoff, then raises a typed
      error naming the URL and attempt count (assert on the error's fields,
      not just that *an* exception occurred).
- [ ] Deadline enforcement test: a stubbed transport that always hangs past
      `response_timeout_sec` raises `DeadlineExceededError`, not a generic
      timeout or an unhandled hang — verified with a bounded test timeout so
      a regression here fails the test suite instead of hanging CI.
- [ ] `watchdog_check()` unit tests: `"ALIVE"` when `now - last_heartbeat <
      timeout_sec`; `"SHUTDOWN"` (with `persist_state()`/`controlled_shutdown()`
      both called exactly once, verified via mocks) when the threshold is
      exceeded.
- [ ] No hardcoded ports, URLs, or timeout values anywhere in
      `mcp_client.py`/`watchdog.py` — all sourced from
      `config/thief/game.toml` in tests via a fixture config.
- [ ] `uv run pytest tests/unit -k "mcp_client or watchdog" --cov` ≥ 85%
      coverage on these modules; `uv run ruff check` clean.

**Stage 5 "Done" milestone (from `TODO.md`, unchanged here):** this Thief
peer plays a full match against a second independent process reachable only
through a public tunnel URL — no localhost shortcut — matching the "two
students over the internet" scenario.

---

## Open items carried over
- The Stage-1 "stuck = captured" rule ambiguity (`PRD_1_base_logic.md` §4)
  remains unresolved — not touched here, must be settled before Stage 6.
- `shared/watchdog.py` is a **new module not in `PLAN.md`'s original layout**
  (§2.3) — `PLAN.md` §1's module list should be updated to include it under
  `shared/` the next time that file is revisited, so the two documents stay
  in sync.
- The Watchdog's heartbeat *producer* side depends on `peer/runtime.py`,
  which isn't fully built until later stages — this PRD builds the checker
  and its unit tests now, but full end-to-end wiring (real heartbeat updates
  from a running match) should be re-verified once `PeerRuntime` is complete.
