# PRD — Stage 6: Commit-Reveal Crypto Sealing + Step-0 Declaration

**Status:** DRAFT — pending approval before implementation
**Stage:** 6 of 7 (see `TODO.md`)
**Book reference:** Chapter 5 — "Cryptographic Security and Zero-Knowledge
Protocol"
**Modules covered:** `domain/crypto.py`, `domain/negotiation.py`,
`domain/game_ids.py`, `peer/sealing.py`, `peer/handshake.py`

---

## 1. Purpose & Theoretical Background

There is no judge (book's founding principle, Ch.1/2), so trust between two
mutually-distrusting peers cannot rest on good faith — it must rest on
mathematics. The book names three concrete temptations a no-referee P2P
system invites (Ch.5.2): changing an already-decided move after seeing the
opponent's, retroactively reinterpreting a declared intent, and reneging on
a claim once it's inconvenient. **Commit-Reveal over SHA-256** closes all
three: a peer locks in a cryptographic fingerprint of its move *before*
either side has seen the other's, and only proves what that fingerprint
meant after both sides are already committed — so switching a decision after
the fact is provably detectable, not just discouraged.

This stage also builds **Step-0** (Ch.5.5): a signed pre-match declaration
of hardware and exact code version, addressing a fairness question the book
raises directly — is it fair for a peer running a powerful dedicated machine
to compete under the same scoring as one on a modest laptop? *Computational
Fairness* (tied into league scoring, Ch.9) rewards algorithmic efficiency,
not raw hardware.

---

## 2. Detailed Description

### 2.1 The four-stage protocol per step (book Ch.5.3, mandatory sequence)
1. **Commit** — send only `H_commit`, never the content.
2. **Acknowledge** — opponent confirms receipt/lock-in, preventing the
   sender from backing out; reveal only happens once *both* sides have
   locked in.
3. **Reveal** — send the actual `Move` + hint text; **Nonce stays hidden**
   at this stage, preventing reverse-engineering of the commitment early.
4. **Final Reveal / Audit** (end of match only) — all Nonces revealed at
   once, enabling full retroactive verification of every step.

The gap in time between Commit and Reveal is what makes cheating provable:
a move is locked before either side even knows the other's move; peeking
then switching would require a hash that doesn't match the one already sent
— caught immediately at audit.

### 2.2 🎯 The exact canonicalization formula (implements `PLAN.md` ADR-3)
This is the concrete implementation of the correction already made in
`PLAN.md`: the book's literal formula (Ch.5.3.1), **not** the lecturer's
sample repo's internal variant (which appends the nonce after the canonical
JSON via `|` instead of embedding it inside the hashed object):

```python
import hashlib, json, secrets

def commit(state, move, intent):
    nonce = secrets.token_hex(16)      # crypto-secure, NEVER the `random` module
    payload = json.dumps(
        {"state": state, "move": move, "intent": intent, "nonce": nonce},
        sort_keys=True, separators=(",", ":"),
    )
    h_commit = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return h_commit, nonce             # send ONLY h_commit now; nonce stays secret

def verify(state, move, intent, nonce, h_commit):
    payload = json.dumps(
        {"state": state, "move": move, "intent": intent, "nonce": nonce},
        sort_keys=True, separators=(",", ":"),
    )
    recomputed = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return secrets.compare_digest(recomputed, h_commit)   # constant-time compare
```

Four fields, all mandatory: `State` (the board-state picture the move is
based on — prevents replaying a commit in a different context), `Move` (the
action itself — what's being locked), `Intent` (the truth/lie flag for the
accompanying hint, declared *in advance* — forces honesty commitment before
the fact, not after), `Nonce` (uniqueness + anti-dictionary-attack, per §2.4).

This is a cross-repo interoperability contract, not an internal detail — the
Cop peer (our teammate's, or any league rival's) must recompute this exact
formula from our revealed data and get an identical digest, or every audit
spuriously fails regardless of correctness.

### 2.3 Mutual audit (book Ch.5.4)
At match end, **each side submits its full log** (every step's
State/Move/Intent, *and now* the Nonce) to the opponent. Critically, this is
**cross**-verification, not self-verification: each side recomputes the
*opponent's* hashes from the opponent's revealed data and compares against
the commit hashes that opponent sent during play. A cheater fabricating a
consistent-but-altered log for themselves gains nothing — the audit only
means something because the *other* side is the one checking. Any mismatch
is provable tampering (SHA-256's avalanche property: a 1-bit change in input
changes the entire digest) → automatic `TECHNICAL_LOSS`, decided by
cryptography, not judgment.

### 2.4 Nonce (book Ch.5.3, "One-Time Random Number")
Dual purpose: (1) ensures the same hash never repeats even for an identical
repeated action, (2) blocks a dictionary attack — without a Nonce, the small
move-space (5 possible moves) would let an eavesdropper precompute the hash
of every possible commit and match it instantly. Generated via `secrets`,
never `random` (the latter is not cryptographically secure).

### 2.5 Step-0 declaration (book Ch.5.5)
Before move 1 of every match, each peer seals and exchanges: OS, CPU
cores/frequency, RAM, GPU/VRAM presence, LLM model name, code version, group
name, match number — **and mandatorily, the exact GitHub commit hash of the
code being played this specific match**. Code may change between matches,
but every match's declaration must record precisely which commit played, so
an auditor can reconstruct exactly what competed. Token consumption is
likewise sealed and reported as evidence of actual computational resources
used — this feeds Computational Fairness league normalization (Ch.9): a
cheap, efficient solution beats a resource-heavy one algorithmically, not by
brute hardware force.

### 2.6 🎯 RESOLVED: the "stuck = captured" ambiguity (carried since `PRD_1`)
This has been flagged as an open item in every PRD since Stage 1, with the
explicit note that it must be settled before this stage seals move records
into the audited log. **It is resolved now, not deferred further**:

Appendix ה states a Thief with "no legal move available" is also counted as
captured. Taken completely literally this is vacuous, since STAY is always a
legal action under the core movement rules (Ch.3) — nobody can ever have
*zero* legal actions. Per the book's own "academic freedom" clause (page 5:
pick a reading, document the contradiction and the choice, and it does not
count against you) — **our final reading, now locked in**: *"stuck"* means
no legal cell-to-cell **movement** exists (every `MOVE`-type direction is
blocked by a barrier or the board edge), leaving only `STAY` as a technical
option — and that condition is what triggers capture-by-stuck, exactly as
already implemented in `is_captured_by_stuck` (`PRD_1_base_logic.md` §3).
This PRD formally closes the ambiguity: `is_captured_by_stuck`'s existing
Stage-1 implementation is correct as written and is now safe to seal into
the audited log without further re-litigation.

---

## 3. Requirements (Input / Output / Behavior)

### `domain/crypto.py`
| Item | Behavior |
|---|---|
| `canonical_json(payload) -> str` | `json.dumps(payload, sort_keys=True, separators=(",", ":"))` — the single shared serialization used everywhere hashing happens |
| `class CommitReveal` | `seal(payload) -> {"nonce", "commit"}` (generates fresh nonce via `secrets.token_hex(16)`); `commit_of(payload, nonce) -> str`; `verify(payload, nonce, commit) -> bool` (via `secrets.compare_digest`, never `==`) |
| `audit_records(records: list[dict]) -> dict` | re-verifies every `{payload, nonce, commit}` entry from a revealed opponent log; returns `{"passed": bool, "verified_steps": int, "failed_steps": list[int]}` |

### `domain/negotiation.py`
| Item | Behavior |
|---|---|
| `Negotiation.signed(terms) -> {"terms", "nonce", "commit"}` | reuses `CommitReveal.commit_of` (`PLAN.md` ADR-6, DRY) to seal the shared `game.json` terms before any port opens |
| `verify_peer(their_terms, their_nonce, their_commit, my_terms)` | recomputes their commit hash **and** asserts `their_terms == my_terms` byte-for-byte — a mismatched config is caught before move 1, not mid-game |

### `peer/sealing.py`
| Item | Behavior |
|---|---|
| `sealed_step_record(state, move, intent) -> dict` | wraps `CommitReveal.seal` with the four required fields, produces the record shape stored in the match log |
| `sealed_spec_record() -> dict` | Step-0 declaration: hardware spec (via `shared/sysinfo.py`, built in Stage 5) + `code_version` + `github_commit_hash` (read from the local git HEAD at startup, not hand-entered) + `group_name` |
| `REQUIRED_TERMS` validation | fail-fast check (`ConfigError`) at startup if any shared `game.json` term needed for sealing (board size, scent constants, etc.) is missing — before any socket opens, per `PLAN.md` ADR-5 |

### `peer/handshake.py`
| Item | Behavior |
|---|---|
| pre-game sequence | exchanges `Negotiation.signed()` terms, then the sealed Step-0 declaration — both complete before move 1 of every match, matching `PLAN.md`'s turn FSM's `NEGOTIATING` state |

### `domain/game_ids.py`
| Item | Behavior |
|---|---|
| `derive_game_id(group_a, group_b) -> str` | deterministic, human-readable identifier (e.g. `"segal-police-team-vs-segal-thief-team"`-style) |
| `derive_game_uid(...) -> str` | a shared UID agreed during the handshake, stitching the four report artifacts together (`PLAN.md` §5) |

---

## 4. Limitations, Constraints, Alternatives Considered

- **Why `secrets.compare_digest`, not `==`, for the final hash comparison:**
  a naive `==` string comparison on hex digests is vulnerable in principle to
  timing side-channels (early-exit comparison leaks information about how
  many leading characters matched); `compare_digest` runs in constant time
  regardless of where a mismatch occurs. Cheap to do correctly, so there's
  no reason not to.
- **Why the Nonce is generated via `secrets`, never `random`:** `random` is
  a deterministic PRNG seeded predictably in some contexts — not
  cryptographically secure. `secrets` is the standard library's
  cryptographically-secure source, and the book explicitly calls this out
  (Ch.5.3, code sample comment) as a correctness requirement, not a style
  preference.
- **Why `github_commit_hash` is read from git HEAD, not entered by hand in
  config:** a hand-entered value could drift from what's actually running
  (forgotten update after a commit) — reading it programmatically at startup
  guarantees the Step-0 declaration always reflects the code that's
  literally executing this match, which is the entire point of the
  declaration (Ch.5.5's "identity matching" mandatory box).
- **Alternative considered and rejected: verify our own log at audit time
  (self-check) instead of only the opponent's.** Self-verification is
  logically vacuous for a genuine cheater — someone who tampered with their
  own history would simply fabricate a self-consistent tampered log. The
  audit's entire value comes from being cross-checked by the party with no
  incentive to let a violation slide; this PRD implements audit as strictly
  opponent-verifies-me, matching §2.3.
- **Alternative considered and rejected: allow the "stuck" ambiguity (§2.6)
  to remain open past this stage, deferring to whichever team disputes it
  first.** Rejected — once move records are sealed and cryptographically
  audited, a disputed rule interpretation becomes a *provable* violation
  claim with no room for renegotiation; resolving it now, in writing, before
  any log is sealed, is strictly safer than resolving it under dispute
  later.

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] `commit()`/`verify()` round-trip: sealing then verifying the same
      `(state, move, intent, nonce)` succeeds; any single-character change to
      any of the four fields causes `verify()` to fail.
- [ ] Formula conformance test: `commit()`'s output matches a hand-computed
      SHA-256 digest for a fixed, hardcoded `(state, move, intent, nonce)`
      tuple — pins the exact canonicalization byte-for-byte, not just
      "produces *a* valid hash."
- [ ] **Tamper test** (already required by `TODO.md` Stage 6): corrupt one
      field in one logged move before running `audit_records()` on it —
      assert the audit reports `passed: False` with that step's index in
      `failed_steps`, and that the rest of an otherwise-clean log still
      passes (partial-failure reporting, not just pass/fail).
- [ ] Nonce source test: static-asserts (via `ast`/import inspection or a
      direct call-source check) that `secrets.token_hex` is used for nonce
      generation and that the `random` module is never imported in
      `domain/crypto.py`.
- [ ] `Negotiation.verify_peer` test: mismatched terms (even a single
      differing value) are rejected before any port opens, with a clear
      error naming the mismatched field.
- [ ] `sealed_spec_record()` test: `github_commit_hash` matches the actual
      current git HEAD in the test environment (via `git rev-parse HEAD`),
      not a stubbed/hardcoded value.
- [ ] `REQUIRED_TERMS` fail-fast test: a `game.json` missing one required
      shared term raises `ConfigError` at startup, before any network call
      is attempted.
- [ ] "Stuck" resolution regression test (closes §2.6): a board state with
      the Thief fully boxed in by barriers/edges (no legal `MOVE`, only
      `STAY` available) is correctly flagged captured by
      `is_captured_by_stuck` — re-run here specifically to confirm the
      Stage-1 implementation still holds now that it's part of the sealed,
      audited path.
- [ ] `uv run pytest tests/unit -k "crypto or negotiation or sealing or
      handshake or game_ids" --cov` ≥ 85% coverage; `uv run ruff check` clean.

**Stage 6 "Done" milestone (from `TODO.md`, unchanged here):** a full match
produces a per-step commit chain on both peers; after the match both peers
independently recompute every hash from revealed nonces and agree PASS; a
deliberately corrupted record is provably caught FAIL; Step-0 declaration is
sealed and exchanged before move 1.

---

## Open items carried over
- **None from Stage 1 remain** — the "stuck = captured" ambiguity is closed
  as of §2.6 above.
- Forward note for `PRD_7_reporting_shell.md`: the sealed Step-0 record and
  per-step commit records built here are exactly the payloads
  `report/artifacts.py` (Stage 7) needs to assemble into the `declaration`
  and `log` JSON artifacts (`PLAN.md` §5) — no new data needs to be
  computed at Stage 7, only packaged.
