# PRD 9 — Cop-Repo Interop Adapter + Scent-Lock Ceremony

Not part of the original 7-stage plan, nor Stage 8's live-match wiring —
built once the Cop repo (`https://github.com/Nagham1023/yamanagh-cop`)
reached its own PRD 10 (CLI + full report bundle), the point at which real
tool-surface comparison became possible against her actual, current code
rather than a moving target.

## 1. Why this exists

Two independently-built peers ended up with a completely disjoint MCP
surface: different tool names, different payload shapes (wrapped `payload`
dict vs. flat kwargs), different scent transport (push-inline vs. pull),
different Step-0 shape (two tools vs. one combined exchange), even
different capture-claim semantics (one-way ack vs. claim/response round
trip). None of this is dictated by the book — each team designed its own
surface. This stage builds a translation layer inside this repo only, no
coordination or changes required on her side, so a real connection attempt
can proceed to the actual turn loop rather than failing on the first call.

## 2. Ch.4.5 scent-lock ceremony (`domain/scent_lock.py`)

The book requires hashing the pheromone formula's *shape* together with its
numbers and a computed worked example (SHA-256), not just the raw
parameters — catches implementation drift (kernel layout, decay order,
rounding) that identical config numbers alone can't. Her repo already
built this (`integrity/scent_model_lock.py`); this module matches her exact
construction (9×9 synthetic board, deposit at (4,4) then (0,0), sample
before/after the second decay round, `.10f` precision, canonical JSON)
byte-for-byte — **empirically verified against her actual cloned source**:
both sides independently compute
`5aac6e62703e2afffac1ad4738fa3f8e2c85da964dbf7a2de17fd3e00d516386` for the
book's default parameters (0.9 / 0.10 / 5). Wired into this repo's own
`negotiate()` (`domain/negotiation.py`) for Thief-vs-Thief matches too —
`Negotiation.signed`/`verify_peer` now carry and check `scent_lock_hash`
alongside the existing Commit-Reveal terms check.

## 3. Shared config schema gap

`config/thief/game.json` was missing `network_and_league` and
`rate_limiter_gatekeeper` — both present in the book's own worked example
(pp.111-113) and in her actual `config/shared/config_dev_g01.json`. Added,
matching both sources' field names/values exactly. Byte-for-byte identity
with her actual file (required for `config_sha256`/rule 11 to ever pass) is
still a one-time coordination step, not something this fix alone
guarantees — her `hash_config_file` hashes raw file bytes, not
re-serialized JSON, so whitespace/formatting must match too.

## 4. Interop package (`src/thief_peer/interop/`)

- **`cop_wire.py`** — pure translation: Step-0 declaration build/sign
  (verified byte-identical against her `sign_step0` —
  `432f16e658a3c12d1324012ab1799180c32ff03e6a28e7608883ed3540ae944c` for a
  fixed test declaration), scent serialize/deserialize (`{"row,col": v}` ↔
  her `{"cells": [[col, row, v], ...]}`, round-trip verified against her
  actual `scent_wire.py`), `hash_config_file`.
- **`cop_handshake.py`** — outbound Step-0 exchange: builds this side's
  declaration, calls her `receive_step0`, then verifies *her* response the
  same way her own `_verify_peer_step0` verifies mine (signature,
  `config_sha256`, `scent_model_sha256`) — a real, working exchange
  whenever the two `game.json` files are actually byte-identical.
- **`cop_turn_sender.py`** — outbound per-turn calls matching her exact
  tool names/shapes: `receive_commit`, `receive_reveal`, `share_scent_map`,
  `receive_final_reveal`, `receive_barrier_declaration`,
  `receive_capture_claim`, `receive_capture_response`.
- **`cop_server_tools.py`** — `CopContextAdapter` + `register_cop_tools`:
  the inbound half, registered on this repo's own FastMCP server alongside
  the native tools. Two tool names collide with pre-existing native ones
  (`receive_barrier_declaration`, `receive_capture_claim` — same names,
  incompatible parameter shapes); the native registration is explicitly
  removed via `mcp.local_provider.remove_tool` before the Cop-shaped one is
  added, so a `cop_v1` server always answers her shape for these two, never
  silently keeps the wrong one underneath (a real bug caught by this
  stage's own live-socket test, not a hypothetical).
- **`cop_round_loop.py`** — `play_round_cop`: her round shape genuinely
  differs (scent is a separate pull, not bundled into reveal; her
  `take_turn` pulls it *before* deciding). A parallel function, not a
  branch inside `peer/round_loop.py::play_round`, so the native
  Thief-vs-Thief path and its existing tests stay untouched.
- **`cop_opponent.py`** — dispatch: `run_opponent_handshake`,
  `play_opponent_round`, `maybe_register_cop_tools`, switched on
  `network.opponent_protocol` (`"native"`, the default, or `"cop_v1"`).
  Kept out of `peer/runtime.py` (already at the 150-line cap) as free
  functions taking `runtime` explicitly.

## 5. Deliberate scope boundary — NOT built

Her per-turn `Hcommit` is a 7-field envelope (`state, move, intent, nonce,
hint_text, step, role`, `integrity/commit_reveal.py`) cryptographically
covering fields this repo's own sealing (`peer/sealing.py::
sealed_step_record`, 3 fields: `state, move, intent`) doesn't. Her
end-of-match audit recomputes `Hcommit` from what a peer revealed using
*her own* algorithm — so this side's own `h_commit` would never verify
against it regardless of wire-shape translation, without rebuilding this
side's sealing to match her exact envelope. Explicitly deferred (see
`interop/__init__.py`'s docstring): `finalize_match` (`peer/match_end.py`)
skips the `submit_audit`/`get_revealed_records` exchange entirely when
`opponent_protocol != "native"` (those tools don't exist on her server at
all) rather than crashing at the very end of an otherwise-successful match;
`audit.passed` reports "not evaluated," not a false pass or false failure.

Also not wired: automatically firing `receive_capture_response` back to her
after receiving `receive_capture_claim` (would need an outbound transport
reference inside an inbound handler — flagged, not built).

## 6. Step-tracking simplification

Her wire messages carry no explicit step number (unlike this repo's own
`commit_move`/`reveal_move` payloads) — she relies on call order matching
turn order. `CopContextAdapter` does the same, via its own independent
counters, rather than coupling to the live round loop's own step variable.
A deliberate, reviewed choice (not hardened against retries or
out-of-order delivery) — correct for a normal, synchronous match.

## Verification

419 tests (27 new this stage), 97% coverage, ruff clean, every new/changed
file at or under 150 lines. Three concrete cross-repo empirical checks
against her actual cloned source (not just internal self-consistency):
scent-lock hash, Step-0 signature, scent wire round-trip — all match.

**Status:** done (wire layer + scent-lock ceremony); per-turn audit
cryptographic compatibility is an explicit, documented non-goal, not an
oversight.
