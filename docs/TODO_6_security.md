# TODO — Stage 6: Commit-Reveal Crypto Sealing + Step-0 Declaration

See `PRD_6_security.md` for full rationale. Book: Ch.5.
PRD milestone: "Move committed and revealed with Nonce; Step-0 hardware evidence ready."

- [ ] `domain/crypto.py`: `canonical_json`, `CommitReveal.seal/commit_of/verify`,
      `audit_records()` — **using the book's exact formula (`PLAN.md` §5, ADR-3)**
- [ ] `shared/sysinfo.py`: `collect_spec()` → OS/CPU/RAM/GPU-VRAM
- [ ] `peer/sealing.py`: sealed spec record (Step-0: hardware + GitHub commit
      hash read from git HEAD + code_version), sealed step record,
      `REQUIRED_TERMS` validation
- [ ] `domain/negotiation.py`: signature exchange reusing `CommitReveal` (ADR-6)
- [ ] `peer/handshake.py`: Step-0 declaration exchanged and sealed before move
      1 of every match
- [ ] `domain/game_ids.py`: deterministic `game_id`/`game_uid` derivation
- [ ] End-of-game `AuditPayload` exchange + `submit_audit` MCP tool + mutual
      hash re-verification (opponent-verifies-me, not self-verification)
- [ ] Tests: tamper test (corrupt one logged move → opponent's audit FAILS);
      assert `secrets` module used for nonces, not `random`; formula-
      conformance test pinning the exact canonicalization byte-for-byte
- [ ] "Stuck = captured" regression test confirming Stage-1's
      `is_captured_by_stuck` is correct now that it's part of the sealed,
      audited path (ambiguity resolved in `PRD_6` §2.6 — closed, not open)

**Done when:** a full match produces a per-step commit chain on both peers;
after the match both peers independently recompute every hash from revealed
nonces and agree PASS; a deliberately corrupted record is provably caught
FAIL; Step-0 declaration is sealed and exchanged before move 1.

**Status:** not started
