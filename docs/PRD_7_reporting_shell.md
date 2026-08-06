# PRD — Stage 7: Reporting Shell (Gmail+OAuth, Live GUI, Replay Simulator)

**Status:** DRAFT — pending approval before implementation
**Stage:** 7 of 7, final stage (see `TODO.md`)
**Book reference:** Chapter 9 — "League, Automated Reporting, Computational
Fairness"; Chapter 7 — "User Interface (GUI) and Replay Simulator";
Appendix א — "Gmail API + OAuth 2.0 Setup Guide"
**Modules covered:** `shared/rate_limiter.py`, `shared/gatekeeper.py`,
`infra/email_sender.py`, `report/artifact_schemas.py`, `report/artifacts.py`,
`report/artifact_helpers.py`, `report/report_writer.py`, `gui/window.py`,
`gui/board_view.py`, `gui/turn_banner.py`, `gui/replay_view.py`, `README.md`

---

## 1. Purpose & Theoretical Background

This is the last of the 7 build stages — the "shell" that turns a locally-
correct peer into something an actual grader (and the actual league) can
observe, trust, and verify from the outside. It has three genuinely distinct
purposes the book keeps deliberately separate rather than folding into one
generic "reporting" feature:

1. **Live observability** (Ch.7.2–7.3): "what's happening *now*?" — a GUI
   that shows only this peer's local truth, never a god's-eye view.
2. **Retrospective, unforgeable witness** (Ch.7.4–7.5): "did what's claimed
   *actually* happen?" — a mandatory Replay Viewer that re-verifies the
   Commit-Reveal chain built in Stage 6, live, step by step.
3. **Automated, mandatory external reporting** (Ch.9): both sides
   independently email a structured JSON match report — and 🎯 **if this
   peer's report isn't received, that game earns zero credit, even if the
   Thief won on the board.** This isn't a nice-to-have; it's a scoring gate.

---

## 2. Detailed Description

### 2.1 Local Truth applies to the GUI too (ties to `PLAN.md` ADR-8)
The book states this as a design principle, not a UI preference (Ch.7.2):
each agent's interface shows *only* what that agent itself legally knows —
its own true position, the belief heatmap it computed about the opponent —
and never a "bird's-eye view" of both true positions at once, because that
would falsify the Dec-POMDP's own partial-observability rule (`Ωi` is a
strict subset of `S`). `PLAN.md` ADR-8 already enforces this at the
protocol level (`TurnMessage` never carries a `position` field) — this stage
just needs the GUI to not accidentally reconstruct it from anything it *is*
allowed to see.

### 2.2 Live GUI: heatmap + turn banner (book Ch.7.3)
- **Heatmap**: renders `BeliefGrid.as_matrix()` (built in Stage 4) as a
  cold→warm gradient — warmer where belief is higher. The Thief's own true
  position (certain) is drawn distinctly from the Cop's *believed* position
  (a shifting probability cloud, never a dot).
- **Turn banner**: a visual manifestation of the turn FSM (`PLAN.md` ADR-2)
  — green "YOUR TURN" when `WAITING_FOR_OPPONENT` transitions to
  `COMPUTING_MOVE` for us, grey "LOCKED" from the moment our Commit is sent
  until the opponent's turn completes. This is not decorative — it's the
  visible proof the state machine is preventing acting out of turn.

### 2.3 Replay Viewer: unforgeable witness (book Ch.7.4–7.5, mandatory)
🎯 **Building this is a mandatory submission requirement, not an optional
architectural nicety** (the book says this explicitly). It loads a saved
match log and steps through it (forward/back), and at every step
recomputes the Commit-Reveal hash live from the now-revealed `(state, move,
intent, nonce)` using the *exact same* `domain/crypto.py` functions built in
Stage 6 — never a separate/duplicated verification routine. Match → green
**"Verified OK"**. Any mismatch, even a single-byte change to past data →
red **"TAMPERED"**, and the match is void immediately, with no appeal — the
whole point of sealing the chain in Stage 6 is that this decision is made by
mathematics (SHA-256's collision resistance), not human judgment.

Two mandatory submission screenshots come directly from this stage: the
Live GUI's heatmap, and the Replay Viewer's "Verified OK" stamp
(book/Appendix ג — already tracked as a checklist item).

### 2.4 The Gatekeeper (book Ch.9.3.1) — one doorway, two consumers
`PLAN.md` ADR-4 already commits to a single shared `ApiGatekeeper` as the
only path to `infra/email_sender.py` **and** `infra/llm_provider.py` (built
in Stage 4). This stage builds the Gatekeeper itself:

- **Token-bucket rate limiter** (book's exact formula):
  `tokens ← min(C, tokens + r·Δt)`, a call is allowed **iff** `tokens ≥ 1`.
- **FIFO queue** on overflow — never silently drop a request, queue it.
- **Retry with backoff** on transient failures, respecting HTTP `429`
  (`Too Many Requests`) specifically — never hammer through it.
- **DOS/infinite-loop detector** — a circuit breaker that hard-locks the
  send path if call volume spikes anomalously (e.g. a bug that emails every
  turn instead of every match), protecting the Gmail account from a ban
  *before* Google notices, not after.
- **Call logging** — every call through the gate is logged, gate or no gate.

### 2.5 Gmail reporting (book Ch.9.3 + Appendix א) — structured JSON only
🎯 **A plain-text report body is explicitly rejected — zero score for that
game.** The report must be a structured JSON file, attached, machine-
readable. Both sides independently send their own report; there's no
dependency on the opponent's report succeeding, but our *own* report not
arriving is a zero-credit outcome regardless of board result. OAuth setup
follows Appendix א exactly (already read in full): `gmail.send`-only scope
(least privilege — never `read`/`modify`), `credentials.json`/`token.json`
both gitignored from the very first commit, Refresh Token enabling
unattended sending after the one-time consent flow.

### 2.6 The four JSON artifacts (book Ch.9, schema already fixed in `PLAN.md` §5)
`report/artifacts.py` assembles, from data already computed in earlier
stages (nothing new computed here, only packaged — see `PRD_6`'s closing
note):
1. **declaration** — Step-0 records (Stage 6) for both groups, once per match.
2. **config** — the shared `game.json` terms verbatim + `config_sha256`.
3. **log** — the full sealed step chain + audit result (Stage 6).
4. **result** — aggregate outcome, `tokens_total_series`, mutual-agreement
   signature.

### 2.7 League bookkeeping (book Ch.9.2.1, Diversity Incentive)
Each match, this peer must **honestly** declare how many counted games it
has already played against this specific opponent group so far — lying
about this count is an explicit disqualification-level offense if caught in
review (book's own wording). This requires a small persisted counter (per
opponent group ID), not just an in-memory value, since it must survive
across separate match invocations.

---

## 3. Requirements (Input / Output / Behavior)

### `shared/rate_limiter.py`
| Item | Behavior |
|---|---|
| `class TokenBucket` | `allow(cost=1.0) -> bool`: implements `tokens ← min(C, tokens + r·Δt)` exactly, refilling lazily on each call rather than via a background timer (simpler, no thread needed) |
| `class DosDetector` | tracks call frequency in a sliding window; raises/locks when a configured anomaly threshold is exceeded (config-driven, never hardcoded) |
| FIFO queue | overflow requests queue rather than drop; queue depth from `rate_limits.json`, never hardcoded |

### `shared/gatekeeper.py` — class `ApiGatekeeper`
| Method | Behavior |
|---|---|
| `execute(api_call, *args, **kwargs)` | routes through `TokenBucket.allow()` first; on `429` specifically, backs off per config and retries up to `max_retries`; on other transient failures, retries once; logs every call attempt (success, retry, or reject) with a timestamp |
| construction | reads all limits from `config/thief/rate_limits.json` — zero hardcoded numbers, per the standing rule |

### `infra/email_sender.py`
| Item | Behavior |
|---|---|
| `send_report(service, recipient, report: dict)` | serializes `report` as a JSON **attachment** (never inlines it as plain-text body) — this is a hard requirement, not a style choice (§2.5) |
| OAuth flow | `token.json` reused if present; first run only triggers the one-time browser consent (Appendix א §1.5); scope restricted to `gmail.send` |
| routed via Gatekeeper | this module is never called directly by `report_writer.py` — only through `ApiGatekeeper.execute()` |

### `report/artifact_schemas.py` / `artifacts.py` / `artifact_helpers.py`
| Item | Behavior |
|---|---|
| `build_declaration(...)`, `build_config(...)`, `build_log(...)`, `build_result(...)` | pure functions assembling the four schemas from `PLAN.md` §5 out of data already produced in Stages 1–6 — no new game logic here |
| `canonical_sha256(payload)` | reuses `domain/crypto.py`'s `canonical_json` (Stage 6, DRY) for `config_sha256` |
| filenames | `declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`, `log_<game_id>_g<NN>.json`, `result_<game_id>.json` — matching book Appendix ו naming exactly |

### `report/report_writer.py`
| Item | Behavior |
|---|---|
| `write_and_send(match_result)` | assembles all four artifacts, writes them to `results/`, and calls `email_sender.send_report` via the Gatekeeper — triggered after **every** legal match, unconditionally |
| league counter | reads/increments the persisted per-opponent games-played counter (§2.7) and includes it honestly in the declaration |

### `gui/window.py` / `board_view.py` / `turn_banner.py`
| Item | Behavior |
|---|---|
| `PeerWindow` | Tkinter root; renders only fields present in `PeerRuntime.view()` — structurally cannot render a Cop position, since that field doesn't exist in the view object (ADR-8) |
| `BoardView` | own true position (certain) + belief heatmap (`as_matrix()`) rendered as a color gradient |
| `TurnBanner` | green/grey per turn-FSM state (§2.2) |

### `gui/replay_view.py`
| Function | Behavior |
|---|---|
| `verify_step(entry) -> str` | recomputes the commit hash from `entry`'s revealed `(state, move, intent, nonce)` via `domain/crypto.py` (Stage 6), returns `"Verified OK"` or `"TAMPERED"` |
| `replay(log) -> str` | walks every step; returns `"TAMPERED"` on the first failure, `"Verified OK"` only if every step passes |
| step controls | forward/back through the loaded log, re-running `verify_step` live per step, not pre-computed once |

### `README.md` (mandatory academic sections, book Ch.9 §9.4.2)
1. Dec-POMDP model description (Ch.1).
2. FastMCP orchestration challenges discussion (Ch.2).
3. Gatekeeper/Orchestrator design explanation (this stage + `PLAN.md`).
4. Strategy used — our custom algorithm, not RL (`PRD_3`).
5. Mandatory screenshots: Live GUI heatmap + Replay "Verified OK".
6. Link to the Cop repo (cross-link, per Ch.9's two-repo submission rule).

---

## 4. Limitations, Constraints, Alternatives Considered

- **Why the token bucket refills lazily on each call, not via a background
  timer thread:** avoids a persistent background thread for a single-process
  peer that isn't otherwise multi-threaded — lazy refill computes the
  elapsed-time top-up at the moment of the call, which is mathematically
  identical to continuous refill and much simpler to test deterministically
  (no sleeping in tests).
- **Why the Replay Viewer re-verifies live, per step, rather than
  pre-computing a single pass/fail once at load time:** matches the book's
  own framing of it as an interactive tool (forward/back through steps) —
  and re-running the same cheap hash check per step keeps the verification
  logic in one place, exercised the same way regardless of navigation order.
- **Why report artifacts compute nothing new (§2.6):** deliberately, to keep
  this stage's actual new surface area small — the risk of subtly
  recomputing a value differently than how it was originally sealed in
  Stage 6 (and thereby producing a report that doesn't match the audited
  log) is exactly the kind of bug this design avoids by construction.
- **Alternative considered and rejected: send the report as inline JSON in
  the email body instead of an attachment.** The book is explicit that
  plain-text bodies are rejected outright; even a JSON-formatted body is
  still textually a "plain text body" from the API's perspective — an
  attachment is the only form that unambiguously satisfies "structured,
  machine-readable, attached file."
- **Alternative considered and rejected: skip the DOS detector since the
  token bucket already rate-limits.** Rejected — the token bucket bounds
  *steady-state* throughput but a runaway bug that fires far more often than
  intended still exhausts the bucket constantly and hammers on `429`s
  indefinitely; the DOS detector is a distinct circuit-breaker for exactly
  that anomalous-pattern case, matching the book's explicit three-part
  Gatekeeper chain (Quota → Rate Limiter → DOS Detector), not a two-part one.

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] **Gatekeeper quota/DOS tests** (already required by `TODO.md`): a
      burst of calls exceeding the token bucket's capacity queues rather
      than drops; a call-frequency spike past the DOS threshold locks the
      gate and raises a distinct, catchable error.
- [ ] **Email-is-always-JSON-attachment test**: `send_report` is asserted to
      always construct a MIME message with a JSON attachment part — a test
      that inspects the constructed message object, not just that "an email
      was sent."
- [ ] **GUI-never-renders-Cop-position test** (already required by
      `TODO.md`, per ADR-8): assert on `BoardView`'s renderer *inputs* — the
      view object passed to it structurally has no position-like field for
      the opponent, so this is a type/attribute-presence check, not a
      behavioral guess.
- [ ] **Replay tamper-detection test** (already required by `TODO.md`):
      feed `replay()` a log with one corrupted step — assert `"TAMPERED"`;
      feed it a clean log — assert `"Verified OK"`; assert `verify_step`
      reuses `domain/crypto.py`'s exact functions (no duplicated hash logic).
- [ ] League counter test: the persisted per-opponent games-played count
      survives a simulated process restart and increments correctly across
      matches against the same vs. a different opponent group.
- [ ] End-to-end smoke test: a full scripted match through Stages 1–6,
      followed by this stage's report-writer, produces all four JSON
      artifacts on disk with matching `game_uid`s, and the Gatekeeper's call
      log shows exactly one email attempt.
- [ ] `uv run pytest tests/unit -k "rate_limiter or gatekeeper or
      email_sender or artifacts or report_writer or gui or replay" --cov`
      ≥ 85% coverage (GUI modules may be excluded from the coverage
      percentage per the guidelines' `omit` convention for GUI code, but
      must still have functional tests); `uv run ruff check` clean.

**Stage 7 "Done" milestone (from `TODO.md`, unchanged here):** after every
legal match this peer automatically emails a structured JSON report via
Gmail through the Gatekeeper without risking a ban; the live GUI shows only
this peer's local truth with a correct async turn banner; a saved log can be
replayed and independently verified as OK or flagged TAMPERED.

---

## Closing note — this is the last of the 7 per-stage PRDs

With this PRD approved, all 7 stages (`PRD_1` through `PRD_7`) are drafted
and consistent with `PRD.md`, `PLAN.md`, and `TODO.md` — the full mandatory
docs-first sequence (`project_standards_and_workflow.md`) is complete. Per
`TODO.md`'s "After Stage 7" section, remaining work is: actual implementation
stage-by-stage (each with its binary milestone before advancing), then the
final pre-submission pass (checklist re-run, ≥2 league matches against
distinct opponents, Git tag, README cross-link verification, secrets audit).
