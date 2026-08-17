# Compatibility with the Imreec league-protocol kit

`github.com/Imreec/copthief-league-protocol` is a second real opponent team's conformance kit,
built against the same underlying rulebook this project targets (`police_thief_p2p.pdf`, Dr.
Yoram Reuven Segal, v3.0.0, University of Haifa) — not just a reference tool. This note records
what our std_v1 implementation (`src/thief_peer/interop/std_v1/`, mirrored in the cop repo's
`src/cop/std_v1/`) already satisfies for that kit, and what to actively confirm once real
coordination (group id, MCP URL) with an Imreec-affiliated peer begins. It complements
`docs/NEXT_OPPONENT_INTEROP_GUIDE_PUBLIC.md` (the "Guide"), which remains the primary spec our
code was built against and which the kit's own core primitives match.

## Already identical — no action needed

Checked against the kit's `SPEC.md`/`WARNINGS.md` against our `crypto.py`, `handshake.py`,
`audit.py`, `series_runner.py`:

- Canonical JSON: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`.
- Commit-reveal: `SHA256(canonical(payload) + "|" + nonce)`, nonce appended outside the hashed
  object.
- `game_uid` = `UUID(SHA256(canonical(terms) + "|" + "|".join(sorted(group_ids)))[:16])`;
  `game_id` = `"-vs-".join(sorted(group_ids))`. Both order-independent, both sort the pair rather
  than naming either side first.
- The 4 MCP tool names and argument names: `negotiate(message)`, `receive_turn(message)`,
  `submit_audit(payload)`, `receive_control(message)`.
- Consensus object shape: 3 top-level keys (`game_id`, `game_uid`, `sub_games`), 5 keys per row,
  group-keyed `roles`/`score`.
- Tie convention: `+2` applied once to each side, only when cumulative totals are equal, at the
  series level (the kit's own "Key Tensions" note names this the resolved/registered choice —
  matches Guide Section 6 exactly, already what `series_runner.py::_row_for`/`report.py` do).

## Points the book leaves ambiguous — already resolved correctly, but worth re-confirming live

- **Scent/pheromone model.** The kit registers two named models: the book's fixed multiplicative
  kernel (`multiplicative_book_v1`) and a "reference" subtractive-Chebyshev alternative
  (`subtractive_chebyshev_v1`). Our `ScentField` (`src/thief_peer/domain/scent.py`, mirrored in
  cop's `src/cop/memory/scent.py`) implements `multiplicative_book_v1` exactly: fixed 5×5 radial
  kernel (centre 0.90; 0.62/0.42/0.20/0.14/0.04 outward), decay-then-deposit
  `τ_next = min(cap, max(0, (1−ρ)·τ_old + δ))` with the cap tied to `emit_intensity` (not a bare
  literal `0.9`). This is the correct, book-faithful choice and needs no code change.
  Cross-team risk: since scent/hints are `[LOCAL]` under the Guide (capture is always
  coordinate-only, never scent-derived), a peer running the other named model cannot break
  scoring or consensus — it can only make each side's own belief tracking noisier. The kit's own
  refusal rule only fires when *both* peers declare a model and disagree; declaring is optional.
  If/when a live Imreec-affiliated handshake starts, confirm what they actually run before relying
  on scent-derived strategy quality, but do not expect it to block a match.
- **Delivery/dedup discipline.** The kit recommends deduplicating retransmitted turns by commit
  hash rather than by `(kind, step)`. Our `StdExchange` keys turns by `step` alone — a resend of an
  identical step message just overwrites with identical content, which is effectively idempotent
  already for this protocol's actual resend pattern (identical payload, same nonce, never
  regenerated). No change made; revisit only if a live peer's resend behavior actually produces a
  step collision with *different* content, which would indicate a protocol violation on their side,
  not ours.

## Before a real match with an Imreec-affiliated team

1. Get their real `group_id` and public `/mcp` URL (Section 3/17 of the Guide — same requirement
   as any std_v1 opponent).
2. Optionally run their kit's own tools against your own artifacts once a practice series exists:
   `python verify_vectors.py` (their reference checker, stdlib-only) and
   `python tools/check_artifacts.py <your-output-dir>` — both are self-contained sanity checks, not
   something this repo needs to depend on or vendor.
3. Run the Guide's own Section 15 non-counted compatibility test first, same as with any opponent.
4. Exchange the `READY_TEMPLATE_STD_V1.md` template (cop repo) before the counted series.
