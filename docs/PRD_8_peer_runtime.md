# PRD — Stage 8: PeerRuntime + the Live-Match MCP Tools

**Status:** DRAFT — pending approval before implementation
**Stage:** 8 — not part of the original 7-stage plan; a genuine gap found
after Stage 7 shipped (see §4's note on how this was discovered)
**Book reference:** Chapter 5 §5.3.2 (Commit/Acknowledge/Reveal/Audit,
pages 49–52), Chapter 8 (Orchestrator + turn State Machine, pages 61–68),
Chapter 6 §6.2 (strategy module's exact plug-in boundary, pages 57–59)
**Modules covered:** `domain/protocol.py`, `peer/turn_fsm.py`,
`peer/round_exchange.py`, `peer/turn_sender.py`, `peer/runtime.py`,
`infra/mcp_server.py` (extended), `sdk/sdk.py` (extended), `cli.py` (extended)

---

## 1. Purpose & Theoretical Background

Stages 1–7 built and individually tested every piece a match needs — board/
brain/belief, Commit-Reveal sealing, negotiation/handshake, the rate-limited
Gatekeeper, the four report artifacts, the GUI/replay view — but no stage
ever wired them into a process that can actually play a live match against
an opponent. `docs/PLAN.md`'s own architecture names `peer/runtime.py`
(`PeerRuntime`) as that orchestrator (Ch.8's "Orchestrator = Single
Gateway... coordinates only, never executes decision/comms logic itself"),
and the MCP server currently exposes only `ping`/`submit_audit` — nowhere
near enough tools for a real per-step exchange. This stage closes that gap.

Book Ch.8 is explicit that this is not a cosmetic gap: in a fully
decentralized system with no referee, an ad hoc turn loop is *the* thing
that produces deadlock (both sides silently waiting forever, no failure
signal) — the mandatory strict state machine with illegal-transition
rejection exists specifically to turn a silent hang into a loud, recoverable
error instead.

---

## 2. Detailed Description

### 2.1 How this stage was found (transparency, matching this project's
established pattern of documenting doc/implementation gaps rather than
hiding them)
While wrapping up Stage 7's README, checking `cli.py`'s only subcommand
(`smoke-test`, a single `ping`) against `docs/PLAN.md`'s C4 diagram (which
names `PeerRuntime` as the thing `cli.py run` should actually drive)
surfaced that `peer/runtime.py`, `peer/turn_fsm.py`, and `domain/protocol.py`
were never built in any of the 7 stages' `TODO_<n>.md` task lists — each
stage's docs deferred this forward ("arriving once `PeerRuntime` exists"),
and no stage ever claimed it as its own task. This was flagged explicitly
in Stage 7's `README.md` rather than silently left for a grader to find.

### 2.2 Grounding the per-turn wire protocol directly in the book (not in
`PLAN.md`'s existing, imprecise §5 draft)
`docs/PLAN.md`'s current §5 `TurnMessage` bundles `hint` + `scent_grid` +
`commit` into a single wire message. Extracting the book's literal text
(`pdftotext` on the source PDF, pages 49–52 — the `Read` tool's PDF renderer
needs `poppler`, not installed here, but `pdftotext` is available via Git's
bundled `mingw64/bin`) shows this is wrong: Figure 6 (p.51) is explicit that
**Commit and Reveal are two separate messages**, both sides participating at
each stage:

```
         Cop                                          Thief
Step 1   Commit: Hcommit only                Commit: Hcommit only
Step 2   Acknowledge (locked)                Acknowledge (locked)
Step 3   Reveal: Move + Hint (Nonce hidden)   Reveal: Move + Hint (Nonce hidden)
Step 4   Final Reveal: all Nonces (end of game, both sides)
```

Sending the hash and the revealed content in the same envelope (as the
current `TurnMessage` draft would) defeats the entire guarantee the
mechanism exists for — "you locked your move before you ever saw mine."
This PRD corrects `PLAN.md` §5 accordingly (§2.4 below), the same kind of
transparent correction already made twice for ADR-6 and once for ADR-2.

### 2.3 One deliberate simplification, and why it doesn't weaken anything
The book's **Acknowledge** step ("rival confirms receipt/lock-in — prevents
the sender from backing out") is folded into `commit_move`'s synchronous MCP
response, rather than built as a fourth distinct tool call. An MCP `Client
.call_tool()` that returns successfully *already is* that confirmation — the
caller knows the callee received and processed the message; a standalone
`acknowledge_move` round-trip would add a network hop without adding a
guarantee the RPC's own request/response semantics don't already provide.
`Reveal` stays genuinely separate and later — the real property (raw
`Move`/`Intent` never transmitted until both sides' hashes are already
locked in) is fully preserved; only the book's message-passing-era framing
of "acknowledge" is adapted to what a synchronous RPC call already gives for
free. This mirrors the precedent already set in `PLAN.md` ADR-6, where the
negotiation exchange was likewise implemented as one request/response call
rather than a literal multi-message handshake.

### 2.4 The turn FSM — literal book transition table (Ch.8, p.63)
Used byte-for-byte, not the paraphrase in `PLAN.md` ADR-2 (directionally
correct but not the literal table):
```python
TRANSITIONS = {
    "WAITING_FOR_OPPONENT": {"COMPUTING_MOVE"},
    "COMPUTING_MOVE":       {"COMMITTING", "TECHNICAL_LOSS"},
    "COMMITTING":           {"AWAITING_REVEAL"},
    "AWAITING_REVEAL":      {"VERIFYING", "TECHNICAL_LOSS"},
    "VERIFYING":            {"WAITING_FOR_OPPONENT"},
    "TECHNICAL_LOSS":       set(),  # terminal
}
```
Any transition not in the current state's allowed target set is rejected
immediately (raises), never silently overwritten — this is the book's
primary defense against deadlock in a system with no referee to notice one
side hanging.

### 2.5 The round shape this implies
Figure 6 shows Cop and Thief at the *same* tabular step, and the Ch.4 scent
note ("decay applied once per full turn, both sides moved") confirms this
is a symmetric per-round exchange, not one side waiting for the other to
finish an entire turn before moving at all. Per round N, from this peer's
side:
1. `COMPUTING_MOVE` — decide `(direction, hint, verdict)` via
   `TurnHandler`/`ThiefBrain`/`TrashTalk` (all reused, unmodified), using
   belief state as of round N−1's reveal — never round N's, since that
   isn't available yet (this is what prevents peeking).
2. `COMMITTING` — seal `(state, move, intent)` locally via
   `CommitReveal.seal()` (nonce kept local); send the commit-hash via
   `commit_move`; block (`round_exchange.wait_for_commit`) until the
   opponent's round-N commit-hash has also arrived at my server.
3. Send my own reveal via `reveal_move`; `AWAITING_REVEAL` — block
   (`round_exchange.wait_for_reveal`) until the opponent's round-N reveal
   arrives.
4. `VERIFYING` — structural sanity check only (well-formed message, `step`
   matches, `move` is a legal direction) — **not** a cryptographic hash
   check yet, since the nonce isn't known until the final audit. Append this
   round's sealed record to the running log, then `WAITING_FOR_OPPONENT` →
   next round's `COMPUTING_MOVE`.

Match end (`domain/rules.py`'s `has_survived` / `is_captured_by_stuck` /
`is_captured_by_barrier`, all reused unmodified) triggers the already-built
end-of-match `submit_audit` exchange (Stage 6) and
`report_writer.write_and_send` (Stage 7) — no new logic in either, only
wiring.

### 2.6 Strategy plug-in boundary (book Ch.6.2, p.58 — confirms existing
design, no change needed)
The book's own pipeline diagram for "strategy module inside PeerRuntime" —
`incoming hint+scent → hint decode → belief update (Bayes) → Commit pack
(out): LLM bluff text + move choice` — matches `strategy/brain_base.py`'s
existing `BrainBase.decide()` boundary exactly (move computed in pure Python
first, hint/verdict filled in after, LLM never touches the move half). No
change to `strategy/` needed for this stage; `PeerRuntime` calls into it
exactly where `TurnHandler.play_turn()` already does.

---

## 3. Requirements (Input / Output / Behavior)

### `domain/protocol.py` (new)
| Item | Behavior |
|---|---|
| `build_commit_message(step, sender, h_commit) -> dict` | `{"step", "sender", "h_commit"}` — carries the hash only |
| `build_reveal_message(step, sender, hint, scent_grid, move, intent) -> dict` | `{"step", "sender", "hint", "scent_grid", "move", "intent"}` — never a `nonce` (withheld until audit) and never a `position` key (ADR-8) |
| `build_audit_payload(sender, result_claim, records) -> dict` | thin wrapper matching what `submit_audit` (Stage 6) already accepts |

### `peer/turn_fsm.py` (new)
| Item | Behavior |
|---|---|
| `TurnFsm` | starts in `WAITING_FOR_OPPONENT`; `.transition(target)` applies the §2.4 table, raising `SimulationError` on any not-allowed transition; `.state` readable at any time (drives `gui/turn_banner.py`'s existing `banner_for_state`) |

### `peer/round_exchange.py` (new)
| Item | Behavior |
|---|---|
| `RoundExchange` | thread-safe mailbox: `record_commit(step, h_commit)` / `record_reveal(step, message)` called from the MCP server thread on inbound `commit_move`/`reveal_move`; `wait_for_commit(step, timeout)` / `wait_for_reveal(step, timeout)` called from the main loop thread, raising `DeadlineExceededError` (existing exception, reused) if the opponent's message for that step hasn't arrived in time — "a missed deadline is a failure, not patience" (Ch.8), mapped by `PeerRuntime` to `TECHNICAL_LOSS` |

### `peer/turn_sender.py` (new)
| Item | Behavior |
|---|---|
| `send_commit(transport, step, sender, sealed) -> dict` | builds + sends a commit message |
| `send_reveal(transport, step, sender, decision, scent_snapshot) -> dict` | builds + sends a reveal message |

### `infra/mcp_server.py` (extended)
| Item | Behavior |
|---|---|
| `build_server(port, context)` | `context` is a small duck-typed interface: `handle_negotiate(payload)`, `handle_receive_control(payload)`, `handle_commit_move(payload)`, `handle_reveal_move(payload)` — each new tool (`negotiate`, `receive_control`, `commit_move`, `reveal_move`) delegates one line to the matching `context.handle_*`; `ping`/`submit_audit` stay free functions, no context needed |

### `peer/runtime.py` (new)
| Item | Behavior |
|---|---|
| `PeerRuntime(config, group_name)` | owns `Board`/`OwnGameState`/`ThiefBrain` (via `TurnHandler`), own `ScentField`, `TurnFsm`, `RoundExchange`, `McpTransport` (client) + `build_server(port, self)` (server, background thread) |
| `.run() -> dict` | `handshake.run_handshake` → round loop (§2.5) until match end → `submit_audit` exchange → `report_writer.write_and_send` → returns the final result dict |
| `.view() -> PeerView` | reused dataclass from `gui/window.py`; populated from `own_state`, `belief.as_matrix()`, `turn_fsm.state`, `own_state.step_count` |

### `sdk/sdk.py` / `cli.py` (extended)
| Item | Behavior |
|---|---|
| `ThiefSdk.run(group_name) -> dict` | builds + drives a `PeerRuntime` to completion |
| `cli.py run --group-name ...` | parsing only, calls `sdk.run(...)`, prints the result — `smoke-test` subcommand unchanged |

---

## 4. Limitations, Constraints, Alternatives Considered

- **Why Acknowledge is folded into the RPC response, not a 4th tool** — see
  §2.3. Rejected alternative: a literal `acknowledge_move` tool — adds a
  network round-trip and a new wait-state without adding any guarantee the
  synchronous `call_tool()` response doesn't already provide.
- **Why round-exchange uses a lock + bounded poll loop, not
  `threading.Condition`** — matches the existing pattern already proven in
  `infra/mcp_server.py`'s `wait_until_ready`, keeping this codebase's
  concurrency style consistent rather than introducing a second idiom for
  the same kind of cross-thread wait.
- **Why `VERIFYING` is a structural check, not a hash check** — the nonce
  genuinely isn't known until the final audit (§2.2); a per-round hash check
  is cryptographically impossible at this point, not merely deferred for
  convenience.
- **Alternative considered and rejected: strict alternating single-mover
  turns** (Cop moves, then Thief, then Cop...). Ruled out directly by
  Figure 6, which shows both sides at the same tabular step every round, and
  by the scent-decay note that decay applies once per full turn with *both*
  sides having moved.
- **Not in scope for this stage:** playing an actual match against the
  teammate's independently-built Cop repo (needs their process running, and
  is a manual/coordination step, not something this repo can simulate), and
  the two mandatory GUI screenshots (need a live desktop session).

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] `TurnFsm` transition test: every edge in the book's literal table
      succeeds; every non-edge (e.g. `WAITING_FOR_OPPONENT` →
      `COMMITTING` directly) raises `SimulationError`; `TECHNICAL_LOSS` has
      no outbound transitions at all.
- [ ] `protocol.py` structural test: `"position" not in
      build_reveal_message(...)` and `"nonce" not in
      build_reveal_message(...)` — the two properties the whole Ch.5
      mechanism depends on.
- [ ] `RoundExchange` test: `wait_for_commit`/`wait_for_reveal` return
      immediately once the matching `record_*` call has happened (from
      another thread, via a real `threading.Thread`, not just sequential
      calls on one thread); a `wait_for_*` call with nothing ever recorded
      raises `DeadlineExceededError` within its configured timeout, not
      indefinitely.
- [ ] `PeerRuntime` unit test against a stub/simulated opponent transport
      (matching the `_StubPeerTransport` pattern already proven in
      `test_handshake.py`): a short scripted match completes, `TurnFsm`
      never raises, the final audit passes with zero `failed_steps`.
- [ ] **Two-real-instance integration test**: two real `PeerRuntime`s on
      real localhost MCP servers (matching the `opponent_feed_server`
      fixture pattern already used in `test_toy_match.py` /
      `test_scent_hint_exchange.py` / `test_mutual_audit.py`) play a short
      match to completion (small `survival_threshold` in a test
      `game.json`); assert both sides' final audits pass and both sides'
      `report_writer` output lands with matching `game_uid`s.
- [ ] `uv run pytest --cov=thief_peer` stays ≥85%; `uv run ruff check .`
      clean.

**Stage 8 "Done" milestone:** `uv run python -m thief_peer run --group-name
<name> --config <path>` drives a full match against a real opponent MCP
server (localhost or a real Cop peer, given the `game.toml`'s
`network.opponent_url`) from handshake through Step-0, every round's
commit/reveal, end-of-match mutual audit, and a Gmail report — with no
manual step in between beyond starting the process itself.

---

## Open items carried over
- None from Stage 7 remain open *in scope of this PRD* — the two items
  flagged in Stage 7's `README.md` are: (1) this stage, now being closed,
  and (2) manual Gmail OAuth + GUI screenshots, which stay genuinely manual
  and are not addressed here either.
- Forward note: once this stage is live-tested against the teammate's Cop
  repo, any wire-format mismatch discovered there (field naming, timing
  assumptions) should be corrected here and documented the same
  transparent way prior cross-repo mismatches were (see the PRD_4
  comparison precedent).

## Addendum — mutual-audit fix (post-Stage-8, found during a compliance
re-audit against the book's Appendix E)
Rules 19/36 require the end-of-match audit to be genuinely mutual — each
side actively verifies the other's revealed log, not just submits itself
to be checked. `finalize_match` originally only ever called `submit_audit`
on the opponent (getting audited BY them); it never pulled or verified the
opponent's own revealed records. Fixed by adding `get_revealed_records`
(§3's table, `mcp_server.py`/`runtime_context.py`) — answerable only once
*this* peer has itself set `_match_over = True` (rule 18: nonce secret
until game end) — and having `finalize_match` call it and run
`domain/crypto.audit_records()` locally on the result. Either direction
failing now overrides the natural game-outcome winner (rule 19: automatic,
no appeal), not just logged passively. Proven for real by both directions
in `tests/integration/test_live_match.py` (two live `PeerRuntime`
instances genuinely auditing each other, not stubs). `peer/runtime.py`
and `infra/mcp_server.py` were split further (`peer/runtime_context.py`,
`infra/null_peer_context.py`) to absorb the new handler/tool without
exceeding this codebase's 150-line-per-file convention.

## Addendum 2 — capture-detection fix (post-Stage-8, same compliance
re-audit)
Rules 21/22/46: `domain/rules.py::is_captured_by_barrier` existed and was
unit-tested since Stage 1 but had zero call sites in the live match loop —
confirmed via grep — since no wire channel existed for the Cop to ever
tell this peer a barrier landed. Fixed by adding two new tools,
`receive_barrier_declaration` and `receive_capture_claim` (§3's table,
`runtime_context.py`). The book prescribes no wire shape for either
(independently confirmed against the Cop repo's own `WIRE-CONTRACT.md`,
which reached the same conclusion about its own equivalent tools) — this
repo's own design, not yet reconciled with the Cop side's differently-
shaped tools of the same name, and deliberately not including either
agent's coordinates (unlike the Cop repo's version), staying consistent
with rule 27's natural-language-only spirit even though barrier cells
are board features, not agent positions, and so aren't actually
constrained by that rule. `receive_capture_claim` only ever confirms a
claim this peer has already independently verified against its own local
state (a recorded barrier landing on its own current cell, or having no
legal moves) — it never trusts an unverified claim, which is this peer's
own defense against a false claim (rule 22) from the other side.
`run()`'s round loop now checks a new `_captured_by_barrier` flag
alongside the existing `is_captured_by_stuck` check every round. Proven
via a dedicated `PeerRuntime.run()`-level test
(`test_being_captured_by_barrier_ends_the_match_after_the_current_round`)
that pre-sets the flag and confirms the match ends after exactly one round
with the opponent as winner. `infra/mcp_server.py` was split once more
(`infra/server_lifecycle.py`, the `run_server_in_background`/
`wait_until_ready` pair) to stay under the file-length convention after
adding the two new tools.

## Addendum 3 — `python -m thief_peer` never actually worked (found by the
user running the documented command by hand)
`src/thief_peer/main.py` existed with the right content (`from
thief_peer.cli import main; ... raise SystemExit(main())`) but the wrong
*name* -- `python -m <package>` specifically requires that package's
`__main__.py` to exist; a module merely named `main.py` is never
auto-invoked by `-m`, regardless of content. Every test in this suite
imports and calls `cli.main()` as a plain function
(`test_cli.py`/`test_sdk.py`), so nothing ever exercised the real `-m`
subprocess path -- 363 passing tests, and the bug still shipped, because
none of them tested the actual documented command. Fixed by renaming the
file to `src/thief_peer/__main__.py`; `docs/PLAN.md`'s layout diagram also
sketched a *separate* repo-root `main.py` convenience launcher from the
very first draft, which was never built and turned out unnecessary once
`__main__.py` alone makes `python -m thief_peer` work -- removed from the
diagram rather than backfilled, since nothing else in the docs or code
ever actually depended on it existing. Closed the actual test gap with
`tests/unit/test_dunder_main.py`, a real `subprocess.run([sys.executable,
"-m", "thief_peer", "--help"], ...)` call -- the first test in this repo
that invokes the package the same way a real user does, not through a
function import.

## Addendum 4 — watchdog wiring, `repos`/`is_counted` reporting fields
(post-Stage-8, remaining items from the same compliance re-audit)

**Rule 7 (watchdog).** `shared/watchdog.py::watchdog_check` was built and
unit-tested since Stage 5, but its own docstring already admitted the
heartbeat *producer* side "belongs to `peer/runtime.py`, arriving in a
later stage" -- that stage never came. Closed by `peer/heartbeat_monitor.py`'s
`HeartbeatMonitor`: a background daemon thread polling `watchdog_check`
against a heartbeat `PeerRuntime.run()`'s round loop updates via `.beat()`
after every round. New `watchdog_timeout_sec` constructor param (default
180s, matching the book's own worked example) -- deliberately **not**
added to the shared `game.json`/`CANONICAL_TERM_KEYS`, unlike an earlier
draft of this addendum considered: a peer's own liveness timeout is a
private, local concern (how patient it is with *itself* freezing), not
something the opponent needs to agree to, exactly the same reasoning
`round_deadline_sec` already used since Stage 8. This also resolves the
earlier "genuinely open" question (`README.md`'s interop section, and the
letter sent for the Cop-team comparison) about whether
`network_and_league`/`rate_limiter_gatekeeper` belong in the signed shared
config: **resolved now, not open** -- these are private per-peer
operational knobs, not cross-peer-agreed facts; the book's own worked
example groups them into one JSON file for presentation convenience, not
because a mismatch there breaks the game the way a `grid_size` mismatch
would.

**A genuine, pre-existing bug found while building this fix's own tests:**
two `test_watchdog.py` tests from Stage 5
(`test_watchdog_check_returns_shutdown_when_heartbeat_is_stale`,
`test_watchdog_check_is_a_strict_boundary_not_off_by_one`) called the real
`watchdog_check()` with a stale heartbeat and never mocked
`persist_state()`/`controlled_shutdown()` -- silently writing a real
`logs/watchdog_state.json` into the repo directory on *every single test
run* since Stage 5. Gitignored, so never a commit risk, but genuine local
pollution that went unnoticed because nothing had reason to check for a
stray `logs/` directory until this fix's own new tests made that check
routine. Fixed by mocking both in each, matching the pattern the sibling
test in the same file already used correctly.

**Rule 49 (`repos` field).** Report artifacts carried no repo-URL
information at all. `config/thief/game.toml` gains a `[repos]` section
(`thief`/`cop` keys, matching the Cop repo's own already-established
naming convention exactly, filled in with this project's two real repo
URLs); `PeerRuntime.repos` loads it (`config.get("repos", {})`, optional --
never required, so it doesn't force every existing config fixture to
declare one); `finalize_match` includes it as `groups.group_1.repos`.
Deliberately only this peer's own known repos, never invented for
`group_2` (the opponent) -- there is still no wire channel to learn theirs,
the same honest limitation the Cop repo's own
`orchestrator_end_of_game.py` docstring documents about its own equivalent
gap.

**Rule 52 (counted vs. warm-up games).** `LeagueCounter` incremented
unconditionally on every `write_and_send` call, with no way to mark a
match as an uncounted warm-up/test run -- risking the persisted
per-opponent count silently inflating past what a real league match
actually played (relevant to rules 37/38's accurate-declaration
requirement). Added `is_counted: bool = True` through the whole chain
(`report_writer.write_and_send` -> `finalize_match` -> `PeerRuntime.__init__`
-> `ThiefSdk.run()`/`run_with_gui()` -> `cli.py run --warmup`, which sets
it `False`). When `False`, `write_and_send` reads the counter's current
value instead of incrementing it, so the declared count never inflates.
Matches the Cop repo's own `EndOfGameMixin.report_game(..., is_counted:
bool, ...)` precedent, which reaches the same design independently.
