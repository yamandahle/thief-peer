# TODO — Fix: round-26/27 MCP connection failure (real cross-machine matches)

Source: Cop side's own investigation note, handed off for the thief-peer
side — `round27-connection-failure.md` (their scratchpad, not this repo).
Verified against this repo's actual code before writing this list (not
taken on faith) — see the "What was verified" section at the bottom.

**Symptom**: real cross-machine matches consistently break around round
26–27 (~30–35s in), both directions at nearly the same moment. Cop side
sees a connect failure sending that round's commit; thief side sees
`Session termination failed: 404` when its client tries to cleanly close
its session at match end. The 404 itself is a harmless side-effect log
line (the server had already dropped the session table entry by the time
the cleanup DELETE arrived) — **do not chase the 404 message directly**,
fix the underlying connection failure instead.

**Leading hypothesis (not fully confirmed)**: a free-tier ngrok
request/connection-rate cap, tripped by request volume (~150+ req/min
against one tunnel by round 26), not a code-level "reconnect per call"
bug — that class of bug was already fixed on both sides earlier (one
persistent `Client`/connection per match).

## 1. Narrow `McpTransport`'s retry scope to provably-safe failures only

**Priority: high. This is a real, independently-confirmed bug, not just a
port of the Cop side's fix.**

`src/thief_peer/infra/mcp_client.py::McpTransport.call()` currently
retries on **any** non-timeout exception raised from `_call_async`. That
is broader than safe: `receive_commit`/`receive_reveal` on the receiving
side (`interop/cop_server_tools.py::CopContextAdapter`) are **not
idempotent** — each call unconditionally does
`self._commit_step += 1` / `self._reveal_step += 1`. If a connection
drops *after* the peer's server received and processed a commit/reveal
but *before* the response reached us, the current retry logic resends
it — the peer's step counter silently double-increments, desyncing round
numbering for the rest of the match. This is exactly the failure class
the Cop side's own retry is already scoped to avoid.

- [x] In `McpTransport._call_async`/`call()`, only retry when the
      failure is **provably pre-transmission** (confirmed against this
      repo's actual installed `fastmcp==3.4.6`/`httpx` — see "What was
      verified" below for exact citations):
      - `httpx.ConnectError`, `httpx.ConnectTimeout`
      - FastMCP's `RuntimeError` wrapper containing `"Client failed to
        connect"` (`fastmcp/client/client.py:623`)
      - FastMCP's `RuntimeError` containing `"Client is not connected"`
        (`fastmcp/client/client.py:381`) — fires before
        `call_tool(...)` can construct the outbound request
- [x] Anything else (a failure surfacing *after* the request may have
      been transmitted — e.g. a dropped connection while awaiting the
      response) must **not** retry: let it propagate as a real
      `TransportError` on the first attempt, same as a hard failure
      today, rather than silently risking a duplicate send.
- [x] Update `McpTransport`'s own docstring to document the narrowed
      scope and why (idempotency of the receiving side's step counters),
      matching how this codebase already documents its other
      correctness-driven design choices.
- [x] Tests (`tests/unit/test_mcp_client.py`): one exercise per
      safe-to-retry exception type (`httpx.ConnectError`,
      `httpx.ConnectTimeout`, both FastMCP `RuntimeError` signatures —
      still retries and eventually succeeds/fails per existing
      behavior), one exercising an *unsafe* exception type asserting it
      propagates immediately on the first attempt with no retry/backoff
      sleep, and the three pre-existing retry tests updated to raise the
      real `httpx.ConnectError` instead of a generic builtin
      `ConnectionError` (which isn't a subclass and would no longer
      qualify as safe-to-retry).

**Implemented** (`src/thief_peer/infra/mcp_client.py`,
`tests/unit/test_mcp_client.py`) — full suite green.

## 2. Defense in depth: duplicate-call protection on our own receiving side

**Priority: medium. Protects us even if the real Cop's own retry policy
over-retries into us — something we can't control on her side.**

Our own `CopContextAdapter.handle_receive_commit`/`handle_receive_reveal`
have the identical non-idempotency problem *in the other direction*: if
her client ever retries a call we already processed, our own
`_commit_step`/`_reveal_step` desyncs the same way.

- [x] `handle_receive_commit`: `h_commit` is `SHA-256({state, move,
      intent, nonce})` with a fresh cryptographically random nonce each
      round (`domain/crypto.py::CommitReveal.seal`) — a *legitimate*
      repeat of the exact same hash across two different rounds is
      astronomically unlikely. Safe heuristic: if the incoming
      `h_commit` exactly matches the one just recorded for the current
      (not-yet-revealed) step, treat as a retry-echo — re-ack
      `{"acknowledged": True}` without incrementing `_commit_step` or
      re-invoking `_context.handle_commit_move` a second time.
- [x] `handle_receive_reveal`: **do not** use the same content-matching
      trick here — `move`/`hint_text` are plain gameplay content and can
      legitimately repeat two rounds in a row (e.g. "STAY" with the same
      generated hint). Use step-boundary tracking instead: a boolean
      "already revealed for the current step" flag, set on a successful
      reveal and cleared only when the *next* `receive_commit` lands: if
      `handle_receive_reveal` fires again while that flag is still set,
      treat as a retry-echo (re-ack, no state mutation).
- [x] Designed with the edge case explicitly in mind: a genuinely
      *differing* `h_commit` while still awaiting the same step's reveal
      is NOT treated as a duplicate (only an exact-match repeat is) — it
      falls through to the normal path, same as before this change.
- [x] Tests (`tests/unit/test_cop_server_tools.py`): a duplicate
      `receive_commit` with identical `h_commit` doesn't double-advance
      `_commit_step` or double-record in `CopPeerTrace`; the same hash
      reappearing *after* its round is genuinely revealed is correctly
      treated as a new round, not suppressed; a duplicate `receive_reveal`
      doesn't double-advance `_reveal_step`; a legitimately repeated
      move/hint in the *next* round (different step) still records
      normally, proving the guard keys off step-boundary, not content.

**Implemented** (`src/thief_peer/interop/cop_server_tools.py`,
`tests/unit/test_cop_server_tools.py`) — full suite green. Exposed one
real test-fixture gap along the way:
`tests/unit/test_runtime.py::_CooperativeCopStubOpponent` only ever
simulated the Cop's `receive_reveal` call landing on our adapter, never
her `receive_commit` — harmless before this change, but with the new
step-boundary guard, every round's identical stubbed reveal content
looked like a retry-echo of round 1 forever. Fixed by having the stub's
`receive_commit` branch also call `handle_receive_commit` on our
adapter, matching what a real cooperative Cop peer actually does each
round (mirrors the exact fixture-gap pattern already noted once before
in this same file's `_CooperativeCopStubOpponent`, for the reveal side).

## 3. Confirm the ngrok rate-limit hypothesis (manual, not code)

**Priority: high — determines whether #4 is worth doing at all.**

- [ ] During a real cross-machine match, watch the local ngrok agent's
      own request log around the round-26/27 window: either the
      terminal output of `ngrok http ...`, or its local admin API
      (`http://127.0.0.1:4040/api/requests/http` while the tunnel is
      running) — look for any `429`, connection-reset, or explicit
      rate-limit event coinciding with the failure.
- [ ] If confirmed: prioritize #4 (or moving off the free ngrok tier for
      real matches) over further retry-logic hardening — the retry
      narrowing in #1/#2 makes failures *safe*, it doesn't make them
      *not happen*.
- [ ] If not confirmed (no rate-limit signal at the failure moment):
      re-open the investigation — the "request volume" theory would be
      falsified, so the real trigger is still unknown and needs fresh
      data (full HTTP-level packet capture or ngrok's own diagnostic
      logging during a reproducing match).

## 4. Reduce per-round request volume (needs cross-team coordination)

**Priority: low/stretch — requires the Cop side to also implement a
matching combined endpoint; not something this side can do unilaterally.**

- [ ] `interop/cop_round_loop.py::play_round_cop` currently does 3
      separate outbound calls per round (`share_scent_map` pull,
      `receive_commit`, `receive_reveal`) — confirmed the volume math in
      the source note's hypothesis matches this repo's actual protocol
      shape exactly (3 round trips × ~30 rounds ≈ the ~90 requests the
      Cop side measured).
  - [ ] Discuss with the Cop side whether a combined
        scent-pull-plus-commit tool (or similar batching) is worth
        adding to the shared `cop_v1` wire vocabulary — a wire-protocol
        change, so it can't be done from this side alone.
  - [ ] Only pursue this if #3 actually confirms a rate/volume cap is
        the real trigger — otherwise this is speculative surgery on a
        working protocol for no confirmed benefit.

## Still outstanding (manual, not code)

- [ ] Consider moving real (non-local-test) matches off the free ngrok
      tier, at least for the specific runs that need to complete a full
      league match without risking a mid-match technical loss from a
      tunnel-side rate cap.

## What was verified (2026-08-16), against this repo's actual code/deps

- `infra/mcp_client.py::McpTransport` already holds one persistent
  `Client`/event loop for the whole match (confirmed by reading the
  current source and its own docstring) — the source note's premise
  that connection-per-call churn is *not* the current bug is accurate
  for this side too.
- `interop/cop_round_loop.py::play_round_cop` does exactly 3 outbound
  calls per round (`cop_request_scent_map`, `cop_send_commit`,
  `cop_send_reveal`) — matches the note's volume claim precisely.
- `httpx.ConnectError`/`httpx.ConnectTimeout` exist in this repo's
  installed `httpx`; the exact strings `"Client failed to connect"`
  (`fastmcp/client/client.py:623`) and `"Client is not connected"`
  (`fastmcp/client/client.py:381`) are both present verbatim in this
  repo's installed `fastmcp==3.4.6` — the note's cited exception
  signatures are real and exact for the version this repo actually uses,
  not approximate.
- `McpTransport.call()`'s current retry-on-any-exception behavior (task
  1's premise) and `CopContextAdapter.handle_receive_commit`/
  `handle_receive_reveal`'s non-idempotent step-counter increments (task
  1 and 2's premise) were both read directly from current source, not
  assumed.

## Update 2 (2026-08-16): a second real match, and the other failure signature

A new match ran after the `technical_loss_reason` fix above landed
(`results/result_dev-team-vs-dev-team-local-test.json`, ended
14:09:35) — and this time `technical_loss_reason` came back `null`
despite the match again ending in a technical loss (27 rounds, again
independently confirmed clean by her audit: `self_audited_by_opponent:
{passed: true, verified_steps: 27}`).

That's not a bug in the new field — it correctly proved this was a
**different failure signature** than Update 1's incident: this time a
record for round 27 *does* exist, meaning the failure was caught
*inside* `play_round_cop` (a `technical_loss=True` return, not an
uncaught exception reaching `PeerRuntime.run()`'s outer catch). That path
never fed anything into `technical_loss_reason` — it only had the
boolean, same gap as before, just in the other half of the code.

**Fixed**: `play_round_cop`/`play_round` now return a 4th value
(`reason: str | None`) alongside `technical_loss`, populated at both of
their internal catch sites (`commit/reveal send failed: ...` /
`opponent's reveal never arrived: ...`) and threaded through
`play_opponent_round` into `runtime.py`, which now sets
`technical_loss_reason` from *either* path. Touched every call site of
both functions (`interop/cop_opponent.py`, `peer/runtime.py`) and their
existing tests (`test_cop_round_loop.py`, `test_round_loop.py`,
`test_cop_opponent.py`, `test_runtime.py`) to unpack/return the new
4-tuple — full suite green. **Both major technical-loss paths now
persist their real reason into the report** — a third match run after
this should finally show *which* of "commit/reveal send failed" or
"opponent's reveal never arrived" actually fired, and the real
exception's type/message underneath it.

## Update 4 (2026-08-16): shared-config wiring audit — network timeouts

A separate critique claimed retry logic must be capped at `response_timeout_sec`
(30s), never the 60s `watchdog_timeout_sec` — checked against the actual
book text (§8.4.1, no "exponential backoff" mandate found, just "controlled
retry") and our own code: no bug of that specific shape existed (network
retries never touched the watchdog timeout at all). But the check surfaced
a real, adjacent bug: **`network_and_league.response_timeout_sec` (30) and
`watchdog_timeout_sec` (60) in the shared `config/thief/game.json` were
never read anywhere in `src/` at all** — `McpTransport.response_timeout_sec`,
`PeerRuntime.round_deadline_sec`, and `PeerRuntime.watchdog_timeout_sec`
were all pure hardcoded class defaults, coincidentally matching (30/30) or
silently diverging (180 vs. the negotiated 60) from the shared config.

A full follow-up audit of all 35 fields in `config/thief/game.json` found
this same pattern in a few other places (see conversation; not all fixed
yet — several are bigger design decisions, e.g. `domain/scoring.py`
ignoring the config's actual per-outcome point table in favor of a
hardcoded win=1/loss=0 scheme, and sub-game series orchestration being
entirely absent from `cli.py`/`sdk.py`).

**Fixed** (this update only): `sdk.py::_build_runtime` now reads
`network_and_league.response_timeout_sec`/`watchdog_timeout_sec` and
passes them into `PeerRuntime(round_deadline_sec=..., watchdog_timeout_sec=...)`;
`PeerRuntime.__init__` now threads its own `round_deadline_sec` into
`McpTransport`'s construction instead of leaving it on a separate,
disconnected default; `sdk.py::smoke_test` does the same. New tests in
`test_sdk.py` pin both the config-present and config-absent-fallback
cases. Full suite green.

## Update 3 (2026-08-16): timestamps + full traceback in the failure reason

A third real match's ngrok inspector data (queried live via the local
admin API, `http://127.0.0.1:4041/api/requests/http`) showed all 101
requests through our own inbound tunnel succeeding cleanly (`200 OK`,
~15ms each) and simply *stopping* ~95 seconds before our own report's
`ended_at` — ruling out a rate cap/rejection on our receiving side for
that run. Correlating "when exactly did our side stop hearing from her"
against "when exactly did our report notice" required manually decoding
the ngrok API's raw base64 request bodies and reading `technical_loss_reason`
's round number — no timestamp on either side made it a direct lookup.

**Added**: `PeerRuntime.run()` now stamps `round_started_at` (UTC
ISO-8601) at the start of every round and includes it directly in
`technical_loss_reason` (`"round N (started <timestamp>): ..."`) for
both the outer catch-all and the two internal-check paths. Also added
`sub_games[].technical_loss_traceback` — the full `traceback.format_exc()`
output, but *only* for the outer catch-all path (a genuinely unexpected
exception, where there's no other "which line" context available;
the two internal checks already say exactly which one fired).

Next real occurrence: the report itself will give an absolute timestamp
directly comparable against ngrok's own request log timestamps, no
manual correlation needed, plus a full traceback if it's an unexpected
bug rather than one of the two known network-failure checks.

## Update (2026-08-16): what the ngrok "ttl=101" screenshot actually shows

A real match was watched live against the ngrok inspector dashboard —
every request up to ttl=101 shows `200 OK`, no `429`/error rows, and the
dashboard simply stops gaining new rows. Investigated against this
match's own real artifacts on both sides (`results/result_dev-team-vs-
dev-team-local-test.json` on this side, `finalProject cop/logs/
result_dev-team.json` on hers — both from the same real match):

- **This side's match ended via `PeerRuntime.run()`'s own outer
  catch-all** (`end_reason="technical_loss"`, mapped to `result:
  "timeout"`), not a max-moves exhaustion or capture. 29 rounds
  completed and were later confirmed clean by her own audit of them
  (`self_audited_by_opponent: {passed: true, verified_steps: 29}`) — the
  failure happened starting round 30, with **no sealed record produced
  for that round at all**.
- That specific signature (`no record` + outer catch) can only come from
  `run_with_deadline`'s deliberately-uncaught propagation in
  `play_round_cop`/`play_round` — every actual network call inside
  either round-loop function (`share_scent_map`/`receive_commit`/
  `receive_reveal`/`wait_for_reveal`) already had a matching internal
  catch that *does* produce a sealed record. (One exception found and
  fixed along the way: native `play_round`'s `send_commit`/`send_reveal`
  pair had **no** catch at all, unlike `play_round_cop`'s identical
  pair — see below.)
- **Reproduced 35 full rounds locally, both protocols, zero network** (a
  throwaway script driving `PeerRuntime` against a cooperative in-process
  stub) — completed cleanly every time. This rules out a plain logic bug
  in `ThiefBrain`/`BeliefGrid` (both bounded by grid size, no growth with
  round count) as the cause — the failure is specific to running over a
  real network/tunnel with a real, independently-paced peer, not
  reproducible synthetically.
- **The Cop's own report for the same match ended ~91 seconds before
  this side's did** (her `ended_at` 12:08:58, this side's 12:10:29,
  matching `started_at` on both sides within ~1 second). That gap is
  consistent with one fully-failed round burning its full cumulative
  budget (scent-pull's own retry budget, then commit/reveal-send's own
  retry budget, then `round_deadline_sec` waiting for a reveal that will
  never come) before finally giving up — each layer bounded and correct
  in isolation, just slow in sequence when the peer has already vanished.
- **Conclusion**: the ngrok connection-cap hypothesis (task 3) is not
  contradicted by this data — a connection-level rejection (vs. an
  HTTP-level `429`) would never show up as a row in the inspector
  dashboard at all, which is consistent with "everything visible is
  `200 OK` and then nothing," not evidence against a cap. Tasks 1/2 are
  doing their job (no crash, no hang past the configured deadlines, a
  full report either way) — they were never meant to fix the underlying
  trigger, only make failure handling safe. Task 3 (checking ngrok's own
  admin API/log *at the exact failure moment*, not just the dashboard
  after the fact, for a `429`/reset) is still the way to actually confirm
  this, and remains open.

**Two more real gaps found and fixed during this investigation:**

- **The actual technical-loss reason was print-only and unrecoverable**
  (`print(f"[technical-loss] ...")`, nothing persisted) — this is why
  pinning down the above required reverse-engineering timestamps across
  two teams' report files instead of just reading the reason. Fixed:
  `peer/runtime.py` now captures it and threads it through
  `finalize_match` into `sub_game_entry["technical_loss_reason"]`
  (`null` for every other end_reason). A recurrence will now show the
  exact exception type/message directly in the written report.
- **`send_opponent_final_reveal`'s outbound call was unguarded** —if the
  round loop already ended because the peer became unreachable, this
  call can hit that same unreachable peer, and an uncaught exception
  here would crash the *entire* match-report sequence (no report at
  all), which is strictly worse than the honest "not evaluated" this
  function already returns for a native-protocol opponent. Fixed in
  `interop/cop_opponent.py` with a matching try/except.
- **Native `play_round`'s `send_commit`/`send_reveal` had no catch at
  all**, unlike `play_round_cop`'s identical pair — a transport failure
  there went straight to the outer catch-all with no sealed record, when
  the book's own transition table has a dedicated
  `AWAITING_REVEAL -> TECHNICAL_LOSS` edge for exactly this. Fixed in
  `peer/round_loop.py` to match.

**New tests** (`tests/unit/test_round_loop.py` — first direct tests of
this shape; `tests/unit/test_runtime.py::
test_run_persists_the_technical_loss_reason_instead_of_only_printing_it`;
`tests/unit/test_cop_opponent.py::
test_send_opponent_final_reveal_survives_an_unreachable_peer_instead_of_crashing`)
— all passing, full suite green.

## Not executed (not code — need the user's own live match / cross-team discussion)

Tasks 3 and 4 above are unchanged from the original plan: #3 needs a real
cross-machine match with the ngrok admin API open to catch the failure
live; #4 needs a wire-protocol discussion with the Cop side before any
code could be written. Neither can be done from inside this session.

**Status:** tasks 1 and 2 (code) done and tested; tasks 3 and 4 (manual /
cross-team) still open
