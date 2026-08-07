# TODO — Stage 6: Commit-Reveal Crypto Sealing + Step-0 Declaration

See `PRD_6_security.md` for full rationale. Book: Ch.5.
PRD milestone: "Move committed and revealed with Nonce; Step-0 hardware evidence ready."

- [x] `domain/crypto.py`: `canonical_json`, `CommitReveal.seal/commit_of/verify`,
      `audit_records()` — **using the book's exact formula (`PLAN.md` §5, ADR-3)**
- [x] `shared/sysinfo.py`: `collect_spec()` → OS/CPU/RAM/GPU-VRAM (GPU/VRAM via
      `nvidia-smi`, honestly `None` when absent — never guessed)
- [x] `peer/sealing.py`: sealed spec record (Step-0: hardware + GitHub commit
      hash read from git HEAD + code_version), sealed step record,
      `REQUIRED_TERMS` validation
- [x] `domain/negotiation.py`: signature exchange reusing `CommitReveal`
      (ADR-6) — refined mid-stage from a bare positional value list to a
      **named** canonical dict (`CANONICAL_TERM_KEYS`), so a mismatch names
      the exact field, not just "something differs" (`PLAN.md` ADR-6 updated)
- [x] `peer/handshake.py`: Step-0 declaration exchanged and sealed before move
      1 of every match — tested via a stub transport backed by a genuinely
      independent second `ConfigManager`, proving the two-sided sequence
      actually works, not just each half in isolation
- [x] `domain/game_ids.py`: deterministic `game_id`/`game_uid` derivation
- [x] End-of-game `AuditPayload` exchange + `submit_audit` MCP tool + mutual
      hash re-verification (opponent-verifies-me, not self-verification) —
      proven over a real live MCP round trip, not just the handler in isolation
- [x] Tests: tamper test (corrupt one logged move → opponent's audit FAILS);
      assert `secrets` module used for nonces, not `random` (static AST check,
      not just behavioral); formula-conformance test pinning the exact
      canonicalization byte-for-byte, and explicitly proving it differs from
      the lecturer-repo's rejected pipe-appended variant
- [x] "Stuck = captured" regression test confirming Stage-1's
      `is_captured_by_stuck` is correct now that it's part of the sealed,
      audited path (ambiguity resolved in `PRD_6` §2.6 — closed, not open) —
      Stage-1's own tests still pass unchanged, plus one new boundary case
      (exactly one direction open) added for this stage's closure

**Also fixed along the way (not originally scoped, but required):**
`ConfigManager` was still TOML-only since Stage 1 — the shared `game.json`
overlay ADR-5 always called for was deferred "until a stage actually needs
it." `negotiation.canonical_terms()` is the first thing that genuinely does;
extended `ConfigManager(toml_path, json_path=None)` to merge both into one
dotted-key namespace (JSON wins on collision — it's signed and shared, the
private TOML must never quietly weaken it).

**Done when:** a full match produces a per-step commit chain on both peers;
after the match both peers independently recompute every hash from revealed
nonces and agree PASS; a deliberately corrupted record is provably caught
FAIL; Step-0 declaration is sealed and exchanged before move 1.

**Milestone met:** ✅ `tests/integration/test_mutual_audit.py` — a real
sealed commit chain submitted over live MCP to an opponent server passes a
clean audit and is caught FAIL (naming the exact tampered step) when
corrupted. `tests/unit/test_handshake.py` proves negotiation-then-Step-0
against a genuinely independent second config. 186 unit+integration tests
passing, 96.1% coverage, ruff clean, all files under 150 lines.

**Status:** done
