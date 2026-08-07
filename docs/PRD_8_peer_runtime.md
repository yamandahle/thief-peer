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
