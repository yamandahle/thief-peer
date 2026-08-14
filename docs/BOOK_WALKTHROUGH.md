# Book walkthrough — section-by-section compliance + enhancement pass

Running log for a full re-read of `police_thief_p2p.pdf` against this
repo, section by section, in parallel with the user's own read of the
book. For each section sent: (1) confirm what this repo already does
against it, citing the exact page/rule, (2) flag any real gap, (3) flag
any legitimate enhancement opportunity (not book-mandated, but a genuine
strategic improvement worth adding), (4) note whether it triggers a new
screenshot/graph requirement for the final submission.

Anything accepted as an enhancement gets logged in the backlog below and
built on the `algorithm-enhancements` branch, one at a time, verified by
a real live match before moving to the next — same discipline as the
Direct Landing fix and the weight-tuning revert earlier in this project.

Anything that should end up written into the actual `README.md` (the
mandatory academic report) gets logged in `docs/README_PLAN.md` instead
of edited into the README immediately — keeps this log and that one
separate: this file tracks compliance/bugs/algorithm ideas, that one
tracks README content specifically.

The book's own final pre-submission checklist (ch.11, p.96-97) is parked
separately in `docs/FINAL_CHECKLIST.md` — deliberately not being worked
through yet, waiting until the section-by-section walkthrough here is
finished, per instruction. It cross-links back to bug-list items where a
checklist box depends on one being fixed first.

## How each entry gets logged

```
### <date> — <book section / page>
**Book says:** <one-line paraphrase, page-cited>
**This repo:** <what exists today, file:line>
**Verdict:** compliant / gap / enhancement opportunity
**Action:** none / added to backlog / built in commit <hash>
**Screenshot or graph needed:** yes/no — <what, and why>
```

## Roadmap note

"Architecture" is split across two separate chapters in the book, covered
as two separate walkthrough parts, not back-to-back:

- **Part 3 = Chapter 2, Network/P2P architecture** (p.8-15) — how the two
  agents talk without a central server. Next up.
- **Chapter 8, internal Agent architecture** (p.61-68) — the Orchestrator,
  state machine, and Watchdog. Comes later in the book; noted here now so
  it isn't lost track of in the meantime.

## Screenshot/graph checklist (cumulative, mirrors rule 42 / ch. 9.4)

Already known, from PRD 7/8 (not yet captured — needs a live desktop):

- [ ] Live GUI belief heatmap — `scripts/watch_prd7_live_gui.py`-equivalent run, window screenshotted mid-match.
- [ ] Replay Viewer "Verified OK" — a genuine untampered match replayed and stamped.

New items get appended here as the walkthrough surfaces them (e.g. a
graph the book's academic-report section asks for, a second replay
screenshot for the tampered case, etc.) — nothing gets removed once
listed, only checked off once actually captured.

## Bugs & fixes to do

One master list now — our own findings plus the Cop team's review of this
repo (`Gaps_to_fix.md`, 2026-08-14), merged and re-verified against the
actual current code (not just trusted as written — two of their 6 items
turned out to be worth a small correction, noted inline). Ordered by how
much it could actually hurt a real match, worst first.

1. ✅ **FIXED (2026-08-14).** ~~We reveal our move before confirming the
   opponent has committed theirs~~ (book ch.5.3.2/Fig.6, p.35-36). Both
   `peer/round_loop.py::play_round` and `interop/cop_round_loop.py::
   play_round_cop` now call `round_exchange.wait_for_commit(step,
   round_deadline_sec)` after sending their own commit and before sending
   their own reveal — a timeout takes the same `COMMITTING` →
   `AWAITING_REVEAL` → `TECHNICAL_LOSS` detour already established for
   send-failures (the book's own transition table, Ch.8 p.63, has no
   direct edge out of `COMMITTING`). Also fixed a real off-by-one that
   would have deadlocked every cop_v1 match: `CopContextAdapter`'s
   `_commit_step`/`_reveal_step` started at 0, one behind the round loop's
   own 1-indexed `step` — moved to start at 1. New tests prove both the
   wait actually happens and that a missing commit correctly reaches
   `TECHNICAL_LOSS` without ever revealing
   (`test_round_loop.py`/`test_cop_round_loop.py`). Two integration-style
   stub opponents in `test_runtime.py` needed updating to simulate sending
   their own commit back, same pattern their existing reveal-injection
   already used. Full suite (762+ tests) passes, ruff clean, coverage
   96.5%.
2. ✅ **FIXED (2026-08-14).** ~~Score isn't zeroed when the audit
   fails~~ (book rule 19, p.129, [FATAL] — "iron law: forging team scores
   0"). `peer/match_end.py::finalize_match` already correctly flipped
   `winner` on a failed audit; now it also forces the forging side's own
   score entry to 0 (`opponent_forged`/`we_forged` flags, reused from the
   existing winner logic), while the honest side keeps whatever the real
   board outcome actually earned it. Covers both directions (we get
   caught / we catch them) and the both-sides-forged edge case. 3 tests
   added/extended in `test_match_end.py`, proving the score actually
   changes (not just the winner label) — e.g. a "captured" outcome that
   would normally give the opponent 20 points now gives them 0 once their
   audit fails. Full suite passes, ruff clean.
3. ✅ **FIXED (2026-08-14).** ~~Retrying a network call can silently
   corrupt the belief map~~ (Cop team, #1). `infra/mcp_client.py::
   McpTransport.call()` now takes a `retryable: bool = True` parameter —
   `retryable=False` skips the retry loop entirely (one attempt only).
   Applied to every state-mutating outbound call in both protocols:
   native `send_commit`/`send_reveal`, and cop_v1's `cop_send_commit`/
   `cop_send_reveal`/`cop_send_final_reveal`/`cop_send_barrier_declaration`/
   `cop_send_capture_claim`/`cop_send_capture_response`. Left retryable:
   `cop_request_scent_map` (a pure read) and the pre/post-game calls
   (negotiate, Step-0, submit_audit, get_revealed_records) — none of
   those accumulate live evidence into a belief map. Matches exactly what
   the Cop team did on their own side, same reasoning, not a different
   fix. New tests at both the `McpTransport` level (proves
   `retryable=False` means exactly one attempt) and the caller level
   (proves every state-mutating sender actually passes it). 5 other test
   files' fake transport stubs needed a `retryable=True` default added to
   their `.call()` signatures to keep matching the real interface. Full
   suite passes, ruff clean.
4. ✅ **FIXED (2026-08-14).** ~~The match report is sent after every
   sub-game, not once at the end of the series~~ (Cop team, #2, book
   ch.9.4). `peer/match_end.py::finalize_match` now reads back whatever
   `result_<game_id>.json` the previous sub-game(s) already left on disk
   (`report_writer.load_previous_result`), merges this sub-game's own
   entry in by `sub_game_number` (`artifact_helpers.merge_sub_games` —
   replace-or-append, so a retried sub-game can't create a duplicate),
   and recomputes the real series totals over the FULL merged list
   (`artifact_helpers.aggregate_series`) — every call, unconditionally,
   since the running state has to persist somewhere between the 6
   separate per-sub-game processes. `write_and_send` gained a
   `send_email: bool = True` parameter; `finalize_match` passes
   `send_email=(sub_game_number >= num_sub_games)`, so only the series'
   actual last sub-game reaches the Gatekeeper/Gmail dispatch — every
   earlier call still writes all 4 files (unconditional) and returns with
   `email_sent: None` (distinct from `False`, a genuinely failed attempt).
   One real design correction made while building this and caught by a
   test that initially failed for the right reason: series
   `winner_group`/`series_tie` must be decided by accumulated *points*
   first (the book's own Tie Rule, p.71 — "if the cumulative score...
   sum of points is equal"), falling back to sub-games-won count only
   when points are exactly equal — deciding by win-count first breaks a
   lone technical-loss sub-game's 0-0-but-still-has-a-fault-based-winner
   case. New tests: a genuine two-sub-game series proving exactly one
   email fires (on sub-game 2, not sub-game 1) and the on-disk file
   correctly accumulates both sub-games' scores; `merge_sub_games`/
   `aggregate_series` unit tests including the points-vs-win-count
   disagreement case. Full suite passes, ruff clean, coverage 96.6%.
4. **The match report is sent after every sub-game, not once at the end
   of the series** (Cop team, #2, book ch.9.4). Confirmed real: `runtime.py`
   → `finalize_match` → `write_and_send` fires unconditionally every
   single sub-game, with no check for "is this the last of the 6." Also
   confirmed worse than their write-up describes in one way: each
   sub-game's `result_*.json` is built fresh from just that one sub-game
   — it never reads back and combines the previous sub-games the way a
   real 6-game series report should (the Cop side already built exactly
   this: `report_bundle_series.py::merge_into_series_result`, offered as
   a reference). One correction to their note, for accuracy: they said
   `tokens_total_series` was a hardcoded `0` and several fields were
   missing entirely — that part's already fixed on our side (those fields
   do exist now), just not accumulated across sub-games yet.

### 🟡 Medium priority — real gaps, lower immediate risk

5. ✅ **FIXED (2026-08-14).** ~~The Cop's moves and barrier placements are
   never checked for legality~~ (our own finding, book ch.3, p.17-22's own
   "Implementation Tip"). Two separate fixes, matching the two separate
   gaps found: **(a) live play** — `domain/rules.py::is_legal_barrier_declaration`
   (on-board + under the agreed `max_barriers` cap) is now checked in
   `peer/runtime_context.py::handle_receive_barrier_declaration` *before*
   recording a barrier; an illegal one raises `SimulationError` instead
   of being silently accepted — FastMCP returns this to the *caller* as a
   failed tool call, it doesn't crash this process or touch our own main
   loop. **(b) the end-of-match audit replay** — `interop/cop_peer_audit.py::_apply`
   now also returns whether the claimed move/barrier was legal, and
   `audit_cop_peer_trace` fails a step on illegality even when its hash
   is honest (previously an off-board move was silently clamped to
   "stayed still," and barrier bounds/count were never checked there at
   all) — this reuses bug #2's score-zeroing fix for free, since an
   audit failure already forces the offending side's score to 0. New
   tests: off-board and cap-exceeding rejections at the live-handler
   level (`test_runtime.py`), and off-board move/barrier plus
   cap-exceeded cases at the audit-replay level (`test_cop_peer_audit.py`),
   plus `is_legal_barrier_declaration`'s own unit tests. Full suite
   passes, ruff clean, coverage 96.75%.
6. ✅ **FIXED (2026-08-14).** ~~The watchdog notices a frozen process but
   doesn't actually stop it~~ (Cop team, #3, rule 7). `shared/watchdog.py::
   controlled_shutdown()` now calls a real `os._exit(1)` — previously it
   printed a message and returned. Deliberately a hard `os._exit`, not
   `sys.exit()`: this runs on the watchdog's own background thread
   (`peer/heartbeat_monitor.py`), and if the *main* thread is genuinely
   frozen (the exact scenario this exists for), `sys.exit()` would only
   raise `SystemExit` in the watchdog thread itself, doing nothing to the
   frozen one — `os._exit()` is the only mechanism that reliably ends the
   whole process regardless of what the main thread is doing. Made
   injectable (`exit_fn` parameter, defaults to the real `os._exit`) so
   tests can spy on it without killing the test runner — the existing
   test that called this directly and checked stdout would otherwise have
   terminated pytest itself the moment this landed; fixed before running
   anything, then verified the full suite genuinely survives it. New
   tests: the injected spy fires with the right code, the *default* (what
   every real caller gets) really is `os._exit`, and a full stale-heartbeat
   → real `watchdog_check` → real `controlled_shutdown` → spied `os._exit`
   path with nothing else stubbed out. Full suite passes, ruff clean,
   coverage 96.75%.
7. ✅ **FIXED (2026-08-14).** ~~Live GUI is missing 2 of the 3 "local
   truth" panels the book describes~~ (Cop team, #6, ch.7.2). `PeerView`
   (`gui/window.py`) gained `scent_matrix`/`hint_text` (defaulted, so no
   existing call site needed updating). A new `gui/scent_view.py::ScentView`
   renders the currently-sensed opponent scent as its own heatmap in a
   deliberately different hue (green) from the existing belief heatmap
   (red/blue) — packed side-by-side with `BoardView` in a shared frame — so
   the two signals never read as one. A new hint-text label sits below the
   turn banner. `PeerRuntime.view()` now populates both from
   `_last_opponent_scent`/`_last_opponent_hint`, via a new pure
   `domain/scent.py::snapshot_to_matrix` helper (sparse dict → dense
   matrix, same shape convention `BeliefGrid.as_matrix()` already uses).
   Still fully rule 8/9-safe — both new fields are this side's own
   already-local data, structurally nothing like an opponent-position
   field. New tests across `test_scent.py`/`test_gui.py`/`test_runtime.py`,
   including one confirming the two heatmap color functions never agree
   on the same value for the same input. Full suite passes, ruff clean,
   coverage 96.76%.

   **📸 Screenshot note: this is the moment flagged earlier — capture the
   Live GUI screenshot now (after this fix), not before.** The window
   looks meaningfully different now (two heatmap panels + hint label
   instead of one panel), so this is the shape that should end up in the
   README.
8. ✅ **FIXED (2026-08-14).** ~~Replay Viewer lets you keep clicking
   "Forward" past a `TAMPERED` step~~ (Cop team, #5, ch.7.4 — "disqualified
   on the first mismatch, no appeal"). `gui/replay_view.py::ReplayView`
   now precomputes the first tampered step's index at construction; `
   step_forward()` refuses to advance past it (repeated clicks stay put),
   and the label reads "... — further steps blocked (disqualified)" once
   you reach it. `step_back()` stays fully unrestricted — reviewing the
   clean history *before* the tamper point is exactly what establishes
   where it happened. Found and fixed a real, previously-passing test
   that was asserting the *old buggy* behavior as if it were correct (it
   stepped past a tampered step and asserted the next, individually-clean
   step read "Verified OK" again — exactly the misleading "it recovered"
   read the book's "no appeal" wording rules out); rewrote it plus added
   6 more covering the blocked-forward, unrestricted-back, tamper-at-the-
   very-first-step, and normal-clean-log cases. Full suite passes, ruff
   clean, coverage 96.76%.
9. ✅ **FIXED (2026-08-14).** ~~Gatekeeper has no daily quota ceiling~~
   (Cop team, #4; book's own Figure 13, p.74). New `shared/rate_limiter.py::
   QuotaManager` — a daily action counter, hard-blocking once the cap is
   reached, resetting on a real UTC calendar-day boundary. Persists to
   disk (mirrors `LeagueCounter`'s own pattern) rather than counting
   purely in memory — a real series spans 6 separate sub-game processes,
   each building a fresh `ApiGatekeeper`; an in-memory-only counter would
   silently hand every sub-game its own full daily allowance instead of
   one shared across the day, defeating the entire point. Caught this
   myself via my own first test before it shipped — an early in-memory
   design passed a test literally named "does not grant a fresh quota on
   restart" while doing exactly that; rewrote it to persist before
   calling it done. Wired into `ApiGatekeeper.execute()` as the *first*
   gate, matching Figure 13's exact order (Quota → Token Bucket → DOS →
   Gmail) — the existing 2 gates were also silently reversed from the
   book's own diagram (ours checked DOS before the bucket); now matches
   exactly. `quota_manager` is opt-in (`None` = disabled, the default) —
   the book gives no concrete daily number anywhere in Appendix F, so
   wiring one into real production use would mean inventing an ungrounded
   value (I6/I9); the architecture is now genuinely available and
   correctly ordered, without smuggling in a number nobody asked for.
   New tests across `test_rate_limiter.py`/`test_gatekeeper.py`: cap
   enforcement, real day-boundary reset, cross-process persistence, and
   the quota gate firing before the token bucket is ever consulted. Full
   suite passes, ruff clean, coverage 96.82%.

### 🟢 Low priority — small hardening, no urgency

10. ⚪ **Reviewed (2026-08-14), decision stands — not a fix.** No
    `--tunnel` convenience flag. Turns out this isn't an oversight: it's a
    deliberate decision made twice (`docs/PRD_5_cloud_tunnel.md` §4,
    revisited and kept in `docs/PRD_10_cop_parity_hardening.md` §6), with
    real book-citation reasoning (ch.2.4 frames starting the tunnel as an
    *operator* action, not something the peer process automates) and an
    explicit "revisit only if the manual-operator model proves
    impractical in a real league match" trigger. That trigger wasn't
    actually hit — this project's earlier ngrok debugging saga was a
    university-network DNS/firewall block, unrelated to manual-vs-
    automated launching; a `--tunnel` flag wouldn't have helped with that
    specific problem either. User's own call, given the full picture:
    leave it as-is rather than reopening an already-closed, reasoned
    decision for symmetry with the Cop repo alone.
11. ✅ **FIXED (2026-08-14).** ~~No check that a negotiated "Minimum"
    value isn't lowered below the book's floor~~ (rule 12). New
    `domain/negotiation.py::MINIMUM_FLOORS` (grid_size:7, max_barriers:14,
    max_moves:35, survival_threshold:35 — PARAMETERS.md Tables 13/15,
    the subset of Minimum-status fields that are actually part of the
    negotiated wire terms). `Negotiation.verify_peer` now rejects an
    agreed value below its floor — the existing symmetry check alone
    couldn't catch this, since it only detects a *mismatch* between the
    two sides, not two teams mutually agreeing on an equally-illegal
    value together, which is exactly what rule 12 forbids.

    **This fix had real fallout worth knowing about**: several existing
    tests (`test_runtime.py`, the real two-socket
    `tests/integration/test_live_match.py`) used a deliberately
    below-floor `grid_size=5`/`survival_threshold=3` for test speed —
    fine when nothing checked the floor, broken once something finally
    did. Fixed surgically: `test_runtime.py`'s 39 tests that never
    negotiate (they call specific handler methods directly) kept their
    original fast fixture untouched; only the 4 that actually call the
    real `.run()` got a new floor-compliant config. `test_live_match.py`
    (a real two-socket integration test with no other tests sharing its
    fixture) got bumped directly — this made it genuinely slower (~3s →
    ~81s, since it now plays a real 35-round match over real sockets
    instead of 3), so it's now tagged `@pytest.mark.slow` — the first
    real user of a marker that existed in `pyproject.toml` but was never
    actually applied anywhere. Full suite passes, ruff clean, coverage
    96.83%.
12. ✅ **FIXED (2026-08-14).** ~~Nothing stops playing the same opponent
    twice for counted-game credit, or checks the minimum-games
    requirement~~ (rules 31/52). Two related, deliberately gentle fixes —
    neither blocks or crashes a match, since these are league-bookkeeping
    rules, not protocol-integrity ones: **(rule 52)** `peer/match_end.py::
    finalize_match` now checks `LeagueCounter.games_played_against(...)`
    before recording — a second counted-game attempt against an already-
    recorded opponent doesn't get a second league credit (prints a clear
    warning naming the rule), but the match's own report/audit/log still
    write and send in full regardless; only the league credit is
    withheld, not the documentation. **(rule 31)** New
    `LeagueCounter.distinct_opponents_played()`, surfaced in a new
    `league_status` block in `finalize_match`'s return value
    (`distinct_opponents_played`, `min_games_to_pass` from config,
    `counted_this_game`) and printed after every match in
    `print_match_summary` — this repo can't force more opponents to have
    been played, only report where things honestly stand so the operator
    can see it after every match instead of having to check by hand.
    New tests across `test_report_writer.py`/`test_match_end.py`: no
    double-credit, warm-ups still repeat freely with no warning, distinct-
    opponent counting across different matches, and the warning message
    itself. Full suite passes (including the real two-socket integration
    test), ruff clean, coverage 96.80%.
13. ✅ **FIXED (2026-08-14).** ~~No 8-character/no-space format check on
    `--group-name`~~ (rule 45 [MUST]). Turned out to be an interpretation
    question, not a straight bug: the book's rule is about a compact
    Moodle-submission code for automatic report attribution, not the
    human-readable display name used everywhere else in logs/GUI/reports
    — forcing `--group-name` itself into 8 characters would've made a
    real team's name unreadable throughout the rest of the system for no
    reason. Asked the user; chose to add it as its own field. New
    `shared/team_code.py::validate_team_code` (exactly 8 characters, no
    whitespace, raises `ConfigError` immediately — never silently
    truncates or strips), a new optional `--team-code` CLI flag
    (validated before `sdk.run`/`sdk.run_with_gui` is ever called), threaded
    through `sdk.py` → `peer/runtime.py` → `peer/match_end.py` →
    `report/artifact_helpers.py::group_block` so it ends up in the actual
    result JSON's `"own"` block as `"team_code"` (`None` when not
    supplied — a dev/warm-up run, never fabricated). New tests:
    `test_team_code.py` (7 cases), plus CLI-level tests proving a valid
    code reaches `sdk.run` and an invalid one raises before `sdk.run` is
    ever called. Full suite passes, ruff clean, coverage 96.82%.
14. ✅ **FIXED for the native protocol (2026-08-14); ⚠️ cop_v1 needs a
    small Cop-side change too — flagged below, nothing touched on that
    side.** ~~games-played-so-far is never declared to the opponent at
    Step-0~~ (rules 37/38, book p.70: "at the start of every game, each
    team declares to its opponent how many counted games it has already
    played"). New `report/report_writer.py::LeagueCounter.
    total_games_played()` (a total across every opponent — distinct from
    rule 31's `distinct_opponents_played()`, which only counts unique
    opponents). Threaded into the Step-0 sealed record itself
    (`peer/sealing.py::sealed_spec_record` gained a `games_played_so_far`
    field) on both sides of a native match: the initiator
    (`interop/cop_opponent.py::run_opponent_handshake`) and the responder
    (`peer/runtime_context.py::handle_receive_control`) each read their
    own real league-counter total and seal it into the declaration they
    send — not just printed after the match, actually part of the
    Commit-Reveal-audited Step-0 exchange. New/updated tests across
    `test_sealing.py`, `test_handshake.py`, `test_runtime.py`,
    `test_report_writer.py`, `test_cop_opponent.py`. Full suite passes,
    ruff clean, coverage 96.83%.

    **cop_v1 (real matches against the Cop teammate) is only half-fixed**,
    and deliberately not touched further: her `receive_step0` MCP tool has
    a strict 3-parameter signature (`declaration`, `signature`, `repos` —
    confirmed by reading `src/cop/tools/mcp_server_prd9.py`), so adding any
    new top-level key to that call — even an unsigned, best-effort one —
    would raise `TypeError: receive_step0() got an unexpected keyword
    argument` on her side and fail the whole handshake. This is a real
    cross-repo wire dependency, not something to route around: closing it
    for cop_v1 needs her `receive_step0` (and `Step0Declaration`/
    `step0_wire.py`) to accept one more field, matching how `repos` (rule
    49) was coordinated between both repos already. **Ask your teammate**
    if/when she's open to adding an optional `games_played_so_far: int`
    parameter to her Step-0 wire — nothing on the Cop side was changed or
    needs to be for this repo's own tests/matches to keep working today.

### 💡 Algorithm enhancement ideas (not bugs — real strategy upgrades)

15. ✅ **FIXED (2026-08-14).** ~~Make the Thief avoid concentrating its own
    scent trail~~ (book ch.1.4, p.6: staying in or returning to a cell only
    makes *that cell's own trail* stronger, which helps the opponent find
    it — a real cost, unlike the verbal hint, which can lie). New
    `strategy/fleeing_brain.py::ThiefBrain._scent_score` (negated intensity
    already recorded at the candidate cell) added as a fifth weighted
    signal (`SCENT_WEIGHT = 0.5`, deliberately kept below `MOBILITY_WEIGHT`
    so it can never override a genuine escape route the way the reverted,
    over-tuned `EXPECTED_DISTANCE_WEIGHT` once did — see this file's own
    corner-camping post-mortem). Fed from the Thief's own pre-move
    `ScentField.snapshot()` (the same trail already sent to the opponent
    every round), threaded through `BrainBase.decide()` →
    `peer/turn_handler.py::play_turn()` → both round loops
    (`peer/round_loop.py`, `interop/cop_round_loop.py`) — no new state, an
    existing signal that simply wasn't reaching the brain before. Not yet
    empirically tuned (ties to item 18 below — the weight is a reasoned
    initial value, not a measured one). New tests in `test_fleeing_brain.py`
    (`_scent_score`'s exact formula, plus a controlled tie-break scenario
    proving the brain picks the least-scented cell when every other signal
    is deliberately equal), updated call sites across `test_brain_base.py`,
    `test_turn_handler.py`, `test_round_loop.py`, `test_cop_round_loop.py`.
    Full suite passes (including the real two-socket integration test),
    ruff clean, coverage 96.84%.
16. ✅ **FIXED (2026-08-14).** ~~Wire up the deception system — it's built
    but never actually runs~~ (book ch.6.5/1.4, "Deception Strategy").
    Both halves fixed: **(a)** `Decision.verdict` is now actually decided,
    not left at its `"truth"` default. New `BrainBase._choose_verdict()`
    hook (default `"truth"`, so a pluggable brain that doesn't model this
    isn't forced to) called from `decide()` itself; `ThiefBrain` overrides
    it to reuse its own private `_expected_distance` — the exact reuse the
    repo's own `runtime.py` docstring had previously flagged as "out of
    proportion to scope" and left undone, now built. **(b)** the hint text
    itself now actually reflects that verdict: `talk_providers.py` gained
    a separate truthful phrase pool alongside the existing (now
    lie-labeled) evasive one, `TemplateProvider.generate()`/
    `TrashTalk.generate_hint()`/`infra/llm_provider.py`'s LLM adapters
    (including the not-yet-live `claude_api`/`claude_cli`/`ollama` prompt
    templates, for whenever that wiring lands) all take the verdict and
    pick accordingly — a lie round asks for something plausible but
    misleading, a truth round asks for something that doesn't mislead.
    New tests across `test_brain_base.py`, `test_fleeing_brain.py`,
    `test_talk_providers.py`, `test_trash_talk.py`, `test_llm_provider.py`;
    updated stubs in `test_round_loop.py`/`test_cop_round_loop.py`. Full
    suite passes (including the real two-socket integration test), ruff
    clean, coverage 96.86%.
17. ✅ **FIXED (2026-08-14).** ~~Notice when the Cop's hint contradicts the
    scent, don't just quietly outweigh it~~ (book ch.4.4, p.24-31).
    `domain/belief.py::observe_hint` already trusted scent enough that a
    lying hint can't win the belief update — that part was already
    correct and untouched. New `domain/hint_direction.py::
    hint_agrees_with_scent(region, scent_snapshot)`: `True` when the
    single most-scented cell falls inside the hint's own parsed direction
    region, `False` when it doesn't (a likely lie), `None` when there's
    nothing to compare (no direction word, or no scent reported yet) --
    never a fabricated verdict. Called once per round from
    `peer/turn_handler.py::play_turn` (reusing the direction cue already
    parsed for the belief update, not a second parse), appended to a new
    `TurnHandler.hint_agreement_log` so the comparison survives past that
    one round instead of being computed and discarded. Surfaced two ways,
    both observability-only (never added to the audited report artifacts,
    which keep the book's own fixed cross-checked schema — same caution
    as the cop_v1 half of item 14): a per-round line in
    `round_reporter.py::print_round_summary` ("AGREES" / "CONTRADICTS
    their scent (possible lie)" / "no signal to compare"), and a
    per-match aggregate in `print_match_summary` ("contradicted their own
    scent in N/M comparable round(s)") — genuinely per-opponent since a
    match/sub-game is already scoped to exactly one opponent. New tests
    in `test_hint_direction.py`, `test_turn_handler.py`, and a new
    `test_round_reporter.py` (this module had no dedicated tests before).
    Full suite passes (including the real two-socket integration test),
    ruff clean, coverage 96.89%.
18. ✅ **DONE (2026-08-14) — experiment redone properly; result is a
    rejection, not an adoption. `fleeing_brain.py`'s constants are
    unchanged.** ~~No real, documented weight-tuning experiment~~ — all
    5 steps of this item's own sequencing plan now complete.

    (a) Prerequisite algorithm changes (15/16/17) landed first. (b)
    `scripts/tuning_cop.py`'s book-baseline Cop now actually places
    barriers (walls the Thief in when adjacent to the believed cell,
    capped at 14) instead of only ever moving — closing the exact
    limitation that made the 2026-08-12 attempt's 77% simulated win rate
    meaningless. Verified directly against a scripted always-STAY Thief:
    captured by step 3. (c) Full 2-pass, 30-trial coordinate-ascent sweep
    run and saved (`docs/weight_tuning_results.json`). Result:
    `expected_distance_weight = 2.0` raised the simulated win rate from
    0.33 to 0.83 against the now-barrier-aware baseline — the *same* knob,
    same direction, as the 2026-08-12 regression. (d) Verified before
    adopting anything: temporarily set the weight to 2.0 locally (never
    committed) and re-ran the existing test suite — two tests failed
    immediately, both specifically built to catch mobility-aware
    corner-avoidance losing to raw distance-maximization, the exact
    mechanism behind the 5/6 real losses last time. A deterministic,
    mechanism-level reproduction of the known failure, found in well
    under a second — decided a live match wasn't needed to reject this
    candidate. Weight reverted immediately. (e) Written up in
    `docs/WEIGHT_TUNING_EXPERIMENT.md`; README section deferred until a
    dedicated pass (`docs/README_PLAN.md` item 8) since the honest
    conclusion is "redid it properly, still correctly rejected it," not a
    new number to report.
19. ⚪ **Decided (2026-08-14): leave as-is, not building anything
    further.** ~~Whether to build something stronger than the current
    1-ply expectimax lookahead~~ — deeper search, or a learned policy —
    now that the Cop side has a live RL brain. The book explicitly treats
    this as optional ("a fully strong agent can be built with heuristics
    alone, RL wasn't even taught in this course"), so this was never a
    compliance item. Revisited once item 18's honest baseline existed, as
    planned — the current `ThiefBrain` stays a pure-Python, weighted-sum
    heuristic with no training pipeline or model artifacts, matching this
    project's existing design and PRD_3 §5's "LLM never touches movement"
    guarantee. This closes the 19-item backlog list: 17 fixed, 1 reviewed
    and kept (#10), 1 closed via a documented experiment (#18), 1 decided
    (#19).

## Section log

### 2026-08-14 — Part 1: The "No-Judge" Reality & Mandatory Constraints (p.iii-iv, 9-12)

**Book says:** No central server/judge; both sides must agree on signed
config terms; only Appendix E/F are binding (not illustrations/snippets);
all agent communication must follow the book's own JSON shapes.

**This repo:** No-server architecture and signed/hashed config negotiation
were already solid (`domain/negotiation.py`). Built `docs/RULES.md`
(Appendix E, 55 rules) and `docs/PARAMETERS.md` (Appendix F) as the
project's own source-of-truth checklist, per this section's own
instruction to never trust paraphrases. Full two-pass code audit against
every rule — results in `RULES.md`.

**Verdict:** mostly compliant. One real gap (score not zeroed on failed
audit/contradictory report, rules 19/35) — see backlog #1. Several small
hardening items — see backlog #2-6. `PARAMETERS.md`: every value in
`config/thief/game.json` matches the book's own example exactly.

**Action:** `RULES.md`/`PARAMETERS.md` created. Backlog item #1 recommended
as the next thing to actually fix (real scoring-integrity bug); rest are
optional hardening, lower urgency.

**Screenshot or graph needed:** no new one from this section — the two
already-known ones (live GUI, replay verified-OK) stay on the checklist
above, still uncaptured.

### 2026-08-14 — Part 2: Modeling the Pursuit (Ch.1, p.1-7)

**Book says:** the game is formally a Dec-POMDP — an 8-part definition
⟨n, S, {Ai}, P, R, {Ωi}, O, γ⟩ (agent count, true state, actions, how the
world changes, rewards, what each side actually observes, and how much
future rounds matter vs. the present). The important teaching in 1.4:
uncertainty isn't only a limitation — it's a weapon both sides can use.
And one specific, concrete point: **a scent trail can't be faked** —
staying in or returning to a cell only makes your own trail *stronger*
there, which is a cost (it helps the opponent find you), never an
advantage. Only the verbal hint can lie; scent can't.

**This repo:** `README.md`'s "Dec-POMDP model" section already explains
the belief-map/partial-observability side well. It doesn't walk through
the book's own 8-part list explicitly, and doesn't mention the "false
hints are legal, faking a scent trail is not" distinction at all — a
worthwhile addition to the README since ch.9's academic report explicitly
wants "dilemmas" discussed, and this is a real one.

**The bigger finding:** `strategy/fleeing_brain.py`'s move-scoring has no
concept at all of "staying/returning here makes my own trail stronger and
easier to find" — the closest thing is a least-recently-visited tie-break,
which only kicks in when two moves already score exactly equal, not a
real cost factored into the score itself. This is the same book insight
that explains *why* the earlier corner-camping bug was so bad — repeatedly
staying in one corner wasn't just a mobility mistake, it was also
maximizing how detectable the Thief was the whole time it sat there.

**Verdict:** compliant (nothing here is a rule), but a genuine, book-cited
enhancement opportunity — added to the backlog as item 13.

**Action:** logged as an enhancement idea, not built yet.

**Screenshot or graph needed:** none for this part.

### 2026-08-14 — Part 3: P2P & Network Architecture (Ch.2, p.8-15)

**Book says:** full decentralization, no central server; every agent is
simultaneously a FastMCP server (exposing tools like `receive_move`) and a
client (calling the opponent's tools); tunneling (ngrok/Localtonet) is
mandatory to cross NAT; Cop and Thief code must run as fully separate
processes with separate config directories, never sharing memory. The
`receive_move` code sample (p.12) that verifies a signature before
trusting a move is explicitly one of the book's non-binding illustrations
(per Part 1's own rule), not a literal required function shape.

**This repo:** clean pass — dual server/client role, process separation,
and Zero-Trust are all already solid (confirmed back in Part 1's rule
audit, rules 1-3). The `receive_move` illustration's real underlying
principle ("verify before you trust") is already handled by the actual
Commit-Reveal design (commit → reveal → audit), not a synchronous
signature check — which is correct, since a move can't be verified before
it's revealed anyway.

**Verdict:** compliant. No new gaps. The only relevant item is the
already-tracked #8 (no `--tunnel` convenience flag) — same gap, nothing
new to add.

**Action:** none needed — confirmed, not skipped.

**Screenshot or graph needed:** none for this part.

### 2026-08-14 — Part 3b: LLM Modes & Deception Strategy (Ch.6.5, p.49-51; ties to Ch.1.4/Ch.5's Intent field)

*(Numbered 3b, not 4 — this one came in without an explicit part number,
between the user's own Part 3 and Part 4; renamed to avoid clashing with
the real Part 4 below, Physical Mechanics & Scoring.)*

**Book says:** four ways to generate the verbal hint layer — template
(free), Ollama (free/local), a paid cloud API, or a CLI-based model — pure
budget choice, movement decision is never affected either way. Separately:
the game log should record each hint's "Intent" (truth or lie), and the
LLM's actual job is to compose a "plausible but misleading" hint that
pulls the opponent away from the real position.

**This repo:** two real findings, both confirmed by reading the actual
code, not guessed.

1. Only `template` mode is wired into a live match today — see the
   corrected table in `PARAMETERS.md`. Not a compliance problem
   (`template` is the book's own recommended default), just a doc
   correction — it previously implied all 4 modes were live options.
2. **The truth/lie decision exists but is dead code.** `choose_verdict()`
   is a real, well-thought-out function — reuses the same
   expected-distance signal the movement brain computes, biased to lie
   more when the opponent's guess is already close. It's just never
   called anywhere; `Decision.verdict` always stays at its `"truth"`
   default. The repo's own `runtime.py` docstring already flags this
   honestly ("Flagged, not hidden"). On top of that, the hint *text*
   itself (`talk_providers.py`'s canned phrases) has zero relationship to
   the verdict either way — so even fixing #1 alone wouldn't yet make the
   hints actually deceptive in content, just honestly labeled.

**Verdict:** not a rule violation (nothing requires hints to lie), but a
real, book-motivated missed opportunity — the deception system the book
describes doesn't currently do anything. Added to the backlog as item 14.

**Action:** `PARAMETERS.md`'s LLM-mode table corrected. Enhancement logged,
not built yet.

**Screenshot or graph needed:** none for this part.

### 2026-08-14 — Part 4: Physical Mechanics & Scoring (Ch.3, p.17-22)

**Book says:** 7×7 grid, top-left origin; orthogonal moves + STAY only,
diagonal = automatic technical loss; the Cop places up to 14 barriers
instead of moving; capture = landing on the Thief's cell OR a barrier
placed on it, either way followed by a Capture Claim; survival = 35 moves;
scoring table as already in `PARAMETERS.md`. Implementation tip: your own
engine must catch it when the *opponent* sends an illegal move (off-board,
into a barrier) — that's meant to be an automatic 0-point loss for them.

**This repo:** grid/movement/scoring all confirmed compliant (checked
against `PARAMETERS.md`/`RULES.md` again — no drift). The capture logic is
exactly the Direct Landing fix from earlier this session — good
confirmation that fix was correct and necessary.

**The new finding:** the Implementation Tip describes catching the
*opponent's* illegal moves, and this repo doesn't do that at all. Checked
every place an incoming Cop move or barrier declaration is handled
(`interop/cop_server_tools.py`, `peer/runtime_context.py`,
`domain/own_state.py::record_barrier`) — none of them check that a barrier
is actually on the board, and none check it against the agreed barrier
limit. Even the end-of-match audit replay (`interop/cop_peer_audit.py::_apply`)
has the same blind spot, and actually silently *hides* one class of
violation — an off-board move is quietly treated as "stayed in place"
instead of being flagged as illegal. Right now, a buggy or dishonest Cop
could place unlimited or off-board barriers and this side would never
object.

**Verdict:** real gap. Added to the backlog as item 4 (medium priority —
same underlying "audit finds a problem but nothing acts on it" family as
item 1, but a distinct kind of check: game-rule legality, not just
cryptographic hash matching).

**Action:** logged, not built yet.

**Screenshot or graph needed:** none for this part.

### 2026-08-14 — Part 5: Digital Pheromones / Scents (Ch.4, p.24-31)

**Book says:** every move (including STAY) leaves a scent trail in a 5×5
zone, center intensity 0.9, decaying radially; the whole trail decays 10%
at the end of every full turn, formula `τij(t+1) = max(0, (1−ρ)τij(t) +
Δτij)`; scent is unforgeable — unlike a hint, it can't lie — so you should
compare hint against scent to catch a lying opponent.

**This repo:** checked the actual formula, the 5×5 kernel values, and the
decay cadence directly against `domain/scent.py` — all confirmed exact,
including STAY still depositing scent (`round_loop.py` calls
`scent.advance()` unconditionally every round). `domain/belief.py` already
gives scent full trust and hints only partial trust, so a lying hint
mathematically can't outweigh real scent evidence in the resulting belief
— the "unforgeable" property is correctly modeled.

**The gap:** "compare scent with hints to detect lying" isn't a formal
rule (it's chapter narrative, not Appendix E), so this isn't a compliance
issue. But it's a real, well-grounded enhancement we're missing: the
comparison happens implicitly in the math every round and is then
discarded — nothing logs it, tracks it, or uses it. Added as backlog item
17, paired with item 16 (your own deception) as the detection-side
counterpart.

**Verdict:** compliant on the physics; a genuine strategy gap on the
lie-detection side.

**Action:** logged, not built yet.

**Screenshot or graph needed:** none for this part.

### 2026-08-14 — Part 6: Cryptography & Fair Play, Commit-Reveal (Ch.5, p.32-40)

**Book says:** SHA-256 Commit-Reveal, 16-byte `secrets.token_hex` nonce
(never `random`), a 4-step protocol per move — Commit (hash only) →
**Acknowledge** (opponent confirms receipt, both sides now locked) →
Reveal (move + hint, nonce still hidden) → Final Audit (all nonces
revealed at match end, replayed and compared). Step-0 hardware + commit
hash declaration for computational fairness. Any single-bit audit mismatch
= automatic Technical Loss for the offender, cryptography decides, not
human judgment.

**This repo:** nonce generation, hashing, canonical JSON, and the richer
7-field envelope all confirmed to match the book's own reference code
exactly. Step-0 hardware declaration already solid (confirmed back in the
Part 1 rule audit, rule 24).

**The real finding:** the Acknowledge step (step 2) is missing from actual
play. `peer/round_loop.py` and `interop/cop_round_loop.py` (the real,
live path against the Cop) both send this side's commit, then immediately
send this side's reveal — never waiting to confirm the opponent's own
commit arrived first. `round_exchange.py::wait_for_commit()` exists,
ready to use, and is simply never called. This defeats the exact purpose
the book explains the Acknowledge step exists for: without it, a slow or
dishonest opponent could see our revealed move before locking their own
commitment, and choose their move with full knowledge of ours.

**Verdict:** real, high-priority gap — promoted to the top of the bug
list (item 1) since it undermines the core security guarantee (ch.5.2's
own "changing a move after the opponent's is revealed" threat) in live
play, not just in reporting.

**Action:** added to backlog as item 1, not built yet.

**Screenshot or graph needed:** none for this part.

### 2026-08-14 — Part 7: GUI & Replay Viewer (Ch.7, p.53-60)

**Book says:** Live GUI shows local truth only (own position, belief
heatmap, opponent's verbal hints) — no bird's-eye view; a Turn Banner
showing "YOUR TURN" vs "LOCKED" once the commitment is sent; Replay
Viewer loads the log, recomputes every hash, shows "Verified OK" or
"TAMPERED" (disqualifying). Two mandatory screenshots for the report:
the Live GUI heatmap and the Replay Viewer's "Verified OK" stamp.

**This repo:** confirmed exact match — `TurnBanner`'s "YOUR TURN"
(`COMPUTING_MOVE` only) vs "LOCKED" (everything else) is byte-for-byte
what the book describes. `BoardView` renders own position + belief
heatmap correctly, structurally unable to show the opponent's true
position. `ReplayView` computes "Verified OK"/"TAMPERED" correctly.

**Update from Part 8 (correction):** Part 8's own direct check of the
book's `GamePhaseMachine` code sketch found it byte-for-byte identical to
`turn_fsm.py`'s transition table — the book's *own* reference state
machine has this same 5-state shape, no separate "waiting on the
opponent's commit" state either. So "the FSM has no slot for Acknowledge"
was slightly overstated as a finding — see Part 8 below for the corrected,
more precise version of this issue (it's about behavior inside the
`COMMITTING` state, not a missing state).

**No new gaps** — this section re-confirms two things already on the
list: the Live GUI is still missing the scent/hint panels (item 7), and
the Replay Viewer still doesn't halt navigation past a tampered step
(item 8).

**Verdict:** compliant, with the two already-known gaps reinforced, not
newly discovered.

**Action:** none new.

**Screenshot or graph needed:** yes, but nothing new — this chapter is
the actual source of the 2 screenshots already on the checklist (Live GUI
heatmap, Replay "Verified OK"), still both outstanding.

### 2026-08-14 — Part 8: Internal Agent Architecture / the Orchestrator (Ch.8, p.61-68)

**Book says:** don't write one long script — split communication, physics,
and strategy into separate modules, coordinated through one central
Orchestrator (a "single gateway" — Figure 12: Orchestrator branching to
MCP Connector, Decision Module, Log Manager, Deadline Tracker, Watchdog;
no module talks to another directly). A strict state machine (the exact
`GamePhaseMachine` code sketch, p.63-64) blocks illegal transitions to
prevent deadlock. Deadline Tracker (per-request timeout) and Watchdog
(whole-process freeze detection) are the two reliability patterns that
turn a hang into a clean technical loss instead of an infinite freeze.

**This repo:** confirmed `PeerRuntime` (`peer/runtime.py`) really is the
single gateway, not just named one — checked directly: `domain/` never
imports `peer/`/`infra/`, `strategy/` never imports `infra/`, and the
network transport/server are only ever constructed in `infra/mcp_server.py`
itself, `PeerRuntime`, and `sdk.py` (which only ever delegates to
`PeerRuntime`, never bypasses it). Matches Figure 12's shape for real.

**turn_fsm.py checked directly against the book's own code sketch (p.63-64)
— byte-for-byte identical**, same 5 states and edges. This corrects Part
7's framing: the missing-Acknowledge issue (backlog item 1) isn't a
missing *state* — the book's own reference FSM has the same shape — it's
that nothing waits for the opponent's commit *inside* the `COMMITTING`
phase before advancing to reveal. Restated more precisely now; same
underlying bug, same priority.

**Watchdog checked against the book's own `watchdog_check()` sketch (p.67)
— matches structurally** (`persist_state`/`controlled_shutdown`/`ALIVE`/
`SHUTDOWN`). The book's own comment on `controlled_shutdown()` says it
should "release MCP connections, close logs" — confirms backlog item 6
(ours only prints) is real, no new finding, just double-confirmed.

**Verdict:** compliant — genuinely well-built to this chapter's own
pattern, confirmed by direct comparison to the book's own code sketches,
not just structural resemblance.

**Action:** corrected Part 7's framing above. No new backlog items — this
part re-confirmed items 1 and 6 more precisely.

**Screenshot or graph needed:** not mandatory (the 2 required screenshots
are the GUI/Replay ones from Part 7), but **worth adding**: a simple
diagram of the Orchestrator + its 5 subsystems, and/or the state-machine
circle, would strengthen the README's model-description section — the
book itself explains this exact chapter with two diagrams (Fig. 11, Fig.
12). Logged as a suggested (optional) addition in `README_PLAN.md`.

### 2026-08-14 — Part 9: League, Gmail Reporting, GitHub Submission (Ch.9, p.69-81)

**Book says:** diversity reward for new opponents, one counted game per
opponent, a game-count declaration made *to the opponent* at the start of
every game; automated Gmail reporting (both sides, independently, JSON
attachment only); the Gatekeeper as 3 layers in a specific order (Figure
13: Quota Manager → Token Bucket → DOS Detector → Gmail API); the exact
`TokenBucket` math; the 4 JSON files' required contents; two GitHub repos,
cross-linked, each containing README/config/PRD/PLAN/TODO; and the
README's 6 mandatory academic-report sections (p.81): the Dec-POMDP model
chosen, FastMCP orchestration dilemmas, strategy implemented, RL learning
curves if applicable, mandatory screenshots, and the companion-repo link.

**This repo, checked point by point:**
- `TokenBucket` matches the book's own reference class exactly (already
  confirmed in Part 6/9 rule audits).
- JSON report structure/field names (`group_id`, not `team_name`;
  envelope fields; hardware spec; mutual agreement hash) already matches
  the book's own reference schema — confirmed back when these were first
  rebuilt this session, re-checked here, no drift.
- Two repos, cross-linked READMEs, config/PRD/PLAN/TODO files — all
  present.
- README's 6 required sections: 5 of 6 present (Dec-POMDP model, FastMCP
  dilemmas — already discusses Gatekeeper/Orchestrator design, strategy
  used, companion repo link; RL curves N/A, not RL-based). Only the
  screenshots are missing — same 2 already tracked, nothing new.

**Two real findings:**
1. **Gatekeeper is missing its 3rd gate, confirmed against the book's own
   diagram this time** (not just the Cop team's review). Figure 13 names
   Quota Manager as the *first* gate, before Token Bucket and DOS
   Detector. Checked `shared/gatekeeper.py::execute()` directly — it only
   has 2 gates, and checks them in the opposite order from the diagram
   (DOS first, then bucket, vs. the book's bucket-then-DOS-after-quota).
   Reinforces backlog item 9, with the extra order detail.
2. **Game-Count Declaration is genuinely missing, not just unclear.** The
   book (p.70) is explicit: "at the start of every game, each team
   declares to its opponent how many counted games it has already
   played." Checked the actual Step-0 payload — no such field exists.
   Upgrades backlog item 14 from UNCLEAR to a confirmed gap.

**Verdict:** mostly compliant, two real gaps — one already known and now
better-specified (item 9), one upgraded from suspected to confirmed
(item 14).

**Action:** items 9 and 14 updated with the confirmed detail above.

**Screenshot or graph needed:** no new screenshot — same 2 as always,
still outstanding. Note for later: did not write the lecturer's report
email address into any file per your request; `config/thief/game.toml`
already has a placeholder recipient from earlier testing, to be updated
when you're ready.

### 2026-08-14 — Part 10: Recommended Development Priorities / the 7-stage roadmap (Ch.10, p.83-90)

**Book says:** build incrementally, one stable layer at a time, each
tested end-to-end before the next: (1) Base Logic, (2) Basic MCP over
localhost, (3) "Blind" heuristic strategy, (4) Scent & Language, (5) Cloud
Tunneling, (6) Full Security/Commit-Reveal, (7) Final Shell (Gmail + GUI +
Replay). Warns explicitly against skipping to crypto/AI before the
networking layer is solid — that's a recipe for a live match freezing or
crashing.

**This repo:** checked `git log --oneline` directly, not just the PRD doc
names — this repo really was built stage-by-stage in the book's own exact
order, one commit per stage (`Stage 1: base logic` → `Stage 2: FastMCP
infra` → ... → `Stage 7: reporting shell`), with Stages 8-10 (PeerRuntime,
Cop interop, hardening) as legitimate, documented additions beyond the
original 7. Real evidence of following the book's own discipline, not
just matching doc titles after the fact.

**Health check requested — ran it:** full test suite passes, `ruff check`
clean, nothing broken by this session's reading/investigation (no code
changed yet, only findings logged).

**Worth connecting:** the book's own warning here — networking must be
solid before crypto/AI gets layered on — is exactly the category backlog
item 1 falls into (a crack in the commit/reveal sequencing, not the
networking itself, but the same "foundation before feature" principle).

**Verdict:** compliant, and unusually well-evidenced.

**Action:** added a suggested (optional) 7-stage timeline diagram idea to
`README_PLAN.md`, backed by real git history, not just narrative.

**Screenshot or graph needed:** not mandatory, but a strong candidate for
an optional diagram — logged in `README_PLAN.md` item 7.
