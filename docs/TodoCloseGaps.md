# TODO — Close the Tier 2/3/4 shared-config gaps (docs/todoFIXMCP.md's audit)

Source: a critique responding to the Tier 2/3/4 findings from
`docs/todoFIXMCP.md`'s full config-wiring audit. **Verified against the
actual book text before writing this list** — two of the critique's
citations don't hold up and are corrected below; the underlying
substance of points 1-4 does, confirmed directly from the PDF.

## Verification notes (read this before implementing)

- **"Mandatory Rule 48" does not exist.** No numbered rule 48 appears
  anywhere in the book. The real citation for the scoring-table
  requirement is **§3.5 "Win Conditions and Scoring" (Table 2), printed
  p.22** — a real table with three rows (successful capture / prolonged
  survival / technical loss), each giving a **separate score to the cop
  and a separate score to the thief** (not a winner/loser split). The
  book's own prose literally flags this as intentional: *"note the
  broken symmetry in the table — capture gives the cop its highest
  reward... but prolonged survival gives the thief its highest reward."*
  Table 2's exact structure (verified, not paraphrased):
  | Outcome | Condition | Cop score | Thief score |
  |---|---|---|---|
  | Successful capture | Cop lands on Thief's cell and declares a Capture Claim | `scoring.capture_cop` | `scoring.capture_thief` |
  | Prolonged survival | Thief survives `survival_threshold` valid steps without capture | `scoring.survival_cop` | `scoring.survival_thief` |
  | Technical loss | Either side crashes, exceeds a deadline, or is caught in cryptographic forgery | `0` | `0` |
  Also confirmed (p.113 area): *"field names are fixed and mandatory; each
  field's **value** may be renegotiated"* — direct textual support for
  Tier 3's concern that hardcoding any of these values (not just scoring)
  is architecturally fragile, even without a single dedicated sentence
  for each field.
- **"Roles switch between sub-games" is not confirmed anywhere in the
  book text I can find.** No mention of mandatory role-alternation
  across a series turned up. Scope this as **an open design choice**
  (matching the critique's own "Design Question... entirely up to you"
  framing for the orchestration mechanism) — don't build automatic
  role-swapping as if it were a confirmed requirement; ask/decide
  separately if it turns out to matter.
- **Tier 4's "must be copied into the outgoing report" claim is only
  partially supported.** `docs/todoFIXMCP.md`'s earlier rulebook research
  already established the book's own canonical `final_result` schema is
  exactly `{total_score, sub_games_won, ties, winner_group, series_tie,
  tokens_total_series}` — it does **not** include `diversity_reward`,
  `min_games_to_pass`, `max_games_per_team`, or `token_budget_per_series`
  at all. These are real config fields with no canonical report slot.
  Copying them into the report as bonus/extension fields is harmless and
  consistent with this repo's existing precedent
  (`games_played_including_this`/`diversity_reward_applied` are already
  handled this way, per `report/series_result.py`) — but it is not a
  confirmed book requirement the way the critique states it.

## 1. Fix `domain/scoring.py` to use the negotiated scoring table (Must fix — confirmed)

**This is a real, previously-wrong design choice** — the README's
existing "Academic freedom: per-sub-game scoring formula" note
(added earlier this session) claims no formula is specified anywhere
available to us. That's wrong; Table 2 is exactly such a formula, and
the shared config's `scoring.*` block carries its literal values
(`capture_cop: 20, capture_thief: 5, survival_cop: 5, survival_thief: 10,
technical_loss: 0`). Scoring every match as a flat winner=1/loser=0
instead produces a real match report with fabricated point values.

- [x] Delete/replace the README's "Academic freedom: per-sub-game
      scoring formula" note (`README.md`) — it's no longer an open
      interpretation question, it's a confirmed miss.
- [x] Rework `domain/scoring.py::score_sub_game`: unlike the current
      `score_sub_game(winner_group, group_a, group_b)` signature (purely
      win/loser based), Table 2 scores **by role** (cop always gets one
      value, thief always gets the other), regardless of who "won" —
      e.g. a captured Thief still gets `survival_thief`... no,
      `capture_thief` (5) points, not 0. New signature needs: the
      `result` value (`"capture" | "survival" | "tamper_forfeit" |
      "timeout"`), which group is playing which role this sub-game
      (`peer/match_end.py` already builds `sub_game_entry["roles"]`),
      and the config's `scoring.*` values. Something like:
      ```python
      def score_sub_game(result: str, roles: dict[str, str], scoring: dict) -> dict:
          # roles: {group_name: "thief"|"cop"}
          cop = next(g for g, r in roles.items() if r == "cop")
          thief = next(g for g, r in roles.items() if r == "thief")
          if result == "capture":
              return {cop: scoring["capture_cop"], thief: scoring["capture_thief"]}
          if result == "survival":
              return {cop: scoring["survival_cop"], thief: scoring["survival_thief"]}
          return {cop: 0, thief: 0}  # technical_loss / tamper_forfeit / timeout
      ```
- [x] Thread the actual `scoring` dict from the shared config
      (per-field `config.get("scoring.<field>", <fallback>)`, matching
      the response_timeout_sec/watchdog_timeout_sec fix's own fallback
      pattern) through `peer/match_end.py::finalize_match` into this
      call.
- [x] `domain/scoring.py::aggregate_series` needed no change — it already
      just sums whatever `sub_games[].score` values it's given.
- [x] Fixed `_RESULT_VALUE`'s `"max_moves_reached"` → now `"survival"`,
      not `"timeout"` — Table 2 has no distinct timeout row, and reaching
      the move cap uncaptured is exactly its survival condition.
- [x] Tests updated: `tests/unit/test_scoring.py` rewritten for the
      role-aware signature; `tests/unit/test_match_end.py`'s
      sub_game_entry score assertions updated to the real Table 2
      values, plus new tests for the max_moves_reached mapping and for
      scoring actually being read from a real config (not just the
      fallback). `test_series_result.py`/`test_report_writer.py` needed
      no changes — their fixtures construct sub_game_entry dicts
      directly rather than calling `score_sub_game`. Full suite green
      (`uv run python -m pytest tests/unit -q`).

## 2. Build sub-game series orchestration (Must fix — confirmed gap, design is open)

Confirmed real: `network_and_league.num_games` (6 in this repo's shared
config) is never read anywhere in `src/`, and `cli.py`/`sdk.py` have no
way to run or report more than "sub-game 1 of 1" per invocation. A real
league match is supposed to synthesize a `sub_games[]` array covering
the whole series (already-existing `report/series_result.py` already
merges by `sub_game_number` across separate report files — the missing
piece is *driving* multiple runs with the right `sub_game_number`/
`num_sub_games`, not the merging itself).

- [x] Mechanism chosen: auto-incrementing counter file (option 3).
      **Implemented**: `report/sub_game_counter.py::SubGameCounter`
      mirrors `LeagueCounter`'s own persisted-JSON pattern exactly
      (peek-vs-record split by `is_counted`, same file-per-`results_dir`
      placement). Keyed by `network.opponent_url` rather than the
      negotiated `game_id` — `sub_game_number` has to be decided and
      sent as part of the very first outbound Step-0 declaration, before
      the opponent's own group name (which `game_id` needs, alongside
      ours) is known at all; `opponent_url` is available from the
      private config up front and uniquely identifies the series.
- [x] `sdk.py::_build_runtime` now reads `num_sub_games` from
      `network_and_league.num_games` (config) and computes
      `sub_game_number` via the counter, passing both into `PeerRuntime`.
- [x] Found and fixed a real bug while wiring this in: `SubGameCounter`
      (like the pre-existing `LeagueCounter`) defaults to a
      cwd-relative path, and was being called unconditionally inside
      `_build_runtime` *before* `PeerRuntime` is even constructed —
      meaning every existing sdk.py test that monkeypatches `PeerRuntime`
      itself would still have hit the real filesystem. Fixed by adding a
      real `results_dir` parameter to `ThiefSdk.__init__` (default
      `"results"`, preserving current real-world behavior exactly),
      threaded into both `SubGameCounter` and `PeerRuntime`'s own
      `results_dir` (also previously never passed from `sdk.py` at all).
      Updated every existing `ThiefSdk(config)` test call site that
      reaches `_build_runtime` to pass `results_dir=tmp_path`.
- [x] Tests: new `tests/unit/test_sub_game_counter.py` (first-call,
      advancing, cross-process persistence, per-opponent independence,
      uncounted-peek behavior); new `tests/unit/test_sdk.py` tests
      proving `num_games` is read and `sub_game_number` genuinely
      advances across repeated `sdk.run()` calls, doesn't advance for
      uncounted runs, and is keyed independently per `opponent_url`.
      Full suite green, confirmed no stray file written to the real
      repo's `results/` directory during the test run.

`cli.py` itself is unchanged — the operator still runs `cli.py run`
exactly as before, once per sub-game, with no new flags to remember;
the counter advances automatically underneath.

## 3. Enforce negotiated board/movement parameters locally (Done — narrower than originally scoped)

Confirmed general principle (p.113 area): config field *values* are
negotiable, only field *names* are fixed. But re-checking the actual
negotiation code before implementing changed the scope significantly:

**Correction to the original audit**: `axis_origin_corner`/`axis_start_index`
(and `max_barriers`) turned out to **already be enforced at negotiation
time**, for both protocols — `domain/negotiation.py::Negotiation.verify_peer`
does a term-by-term comparison over every key in `CANONICAL_TERM_KEYS`
(which includes these three) and raises `ConfigError` on any mismatch
for the native protocol; `cop_v1`'s `config_sha256` (a hash of the
*entire* shared config file) transitively guarantees the same fields
match, since they're part of that byte-identical file. The original
"UNUSED" verdict from the earlier audit was right that nothing *uses*
these values to compute differently, but wrong to imply nothing checks
them — a mismatched opponent already fails cleanly before the match
starts. **No coordinate-transform work needed** — the chosen "narrow"
scope for axis handling turned out to already exist.

What negotiation genuinely *can't* catch: a peer who agrees to a quota
at Step-0 and then violates it mid-match. That's a real, distinct gap,
and it's the only part of this item that needed new code:

- [x] `movement_and_barriers.max_barriers`: `peer/runtime_context.py::
      handle_receive_barrier_declaration` now refuses a barrier
      declaration that would push the count of *distinct* known barrier
      cells past the negotiated `max_barriers` (raises `SimulationError`,
      matching this file's existing rule-violation pattern). Re-declaring
      an already-known cell is correctly a no-op, not counted twice. The
      `cop_v1` interop adapter (`interop/cop_server_tools.py::
      CopContextAdapter.handle_receive_barrier_declaration`) delegates
      straight into this same handler, so it's covered automatically —
      no separate cop_v1-specific change needed. (This repo never places
      barriers of its own — that's a Cop-side game mechanic — so there
      was nothing to add on the "cap our own placement" side of the
      original item.)
- [x] Tests: `tests/unit/test_runtime.py` — accepts exactly up to the
      quota, rejects the one past it (declaration not recorded), and
      confirms re-declaring an existing cell never counts as a new one.
      Full suite green.
- [ ] `movement_and_barriers.move_set`: still just negotiated/verified,
      never locally acted on — but this repo (the thief) never receives
      the Cop's individual moves in a way it could validate against
      `move_set` anyway (the whole point of hidden-state pursuit is not
      knowing the Cop's moves directly, only scent), so there's no
      actionable runtime check to add here the way there was for
      barriers. Left as-is; flagged for completeness only.

## 4. Pass Tier-4 league parameters through to the report (Done)

Not required by the book's own canonical schema (see verification note
above), but cheap and consistent with this repo's existing
bonus-field precedent:

- [x] `peer/match_end.py::finalize_match` reads
      `network_and_league.diversity_reward`/`min_games_to_pass`/
      `max_games_per_team`/`token_budget_per_series` and adds them as
      `match_result["league_params"]` (`None` per field if the config
      section is absent, not silently dropped).
- [x] Threaded through `report/report_writer.py::write_and_send` into
      `report/series_result.py::merge_sub_game_into_series` (new
      `league_params` parameter, defaults to `{}`), which merges them
      into `final_result` alongside the existing
      `games_played_including_this`/`diversity_reward_applied` bonus
      fields. `diversity_reward` (the raw config scalar) is deliberately
      distinct from `diversity_reward_applied` (a boolean, always
      `False`) — same name, different concept, documented inline to
      avoid the same name-collision trap the original audit already
      flagged once.
- [x] Tests: `tests/unit/test_match_end.py` (values genuinely read from
      config, and default to `None` per field when absent);
      `tests/unit/test_series_result.py` (merged into `final_result`,
      absent entirely when no `league_params` supplied). Full suite green.

## Verification

- `cd /home/nagham1023/AI-Agents-course/thief-peer && uv run python -m pytest tests/unit -q`
  must stay green throughout — items 1 and 2 both touch existing,
  already-tested behavior (`domain/scoring.py`, `peer/match_end.py`,
  `cli.py`/`sdk.py`).
- After item 1: manually inspect a real match's written
  `result_<game_id>.json` and confirm `sub_games[].score` matches the
  shared config's actual `scoring.*` values for that match's real
  outcome, not a flat 1/0.
- After item 2 (once a mechanism is chosen): confirm running the chosen
  mechanism `network_and_league.num_games` times produces one
  `result_<game_id>.json` with a `sub_games[]` array of that length, not
  one file per sub-game each showing `num_sub_games: 1`.

**Status:** all four items done, full suite green throughout.
