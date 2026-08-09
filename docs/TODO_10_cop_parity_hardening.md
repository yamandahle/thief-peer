# TODO — Stage 10: Cop-Parity Audit + Cloud-Readiness Hardening

See `PRD_10_cop_parity_hardening.md` for full rationale. Book: rule 20
[FATAL] (replay/verify viewer), rules 28/29 (rate-limiter/DOS gatekeeper),
rule 11 [FATAL] (byte-identical config), rule 10 (public tunnel
reachability). Triggered by a claim from the Cop team's own AI assistant
listing 6 "advanced extensions"; independently verified against her actual
cloned source rather than accepted at face value.

**Verified at parity, no action** (see PRD_10 §2): scent-model SHA-256 lock,
cop_v1 byte-identical config check, live belief-heatmap GUI, zero-token
template hint provider.

## Gap 1 — replay viewer wiring (rule 20, [FATAL])
- [x] `cli.py`: add a `replay` subparser (`--log <path>`, `--gui`)
- [x] `sdk.py::run_replay(log_path, gui=False) -> int`: load the JSON log,
      run `gui/replay_view.py::verify_step()` per record in `data["records"]`,
      print a per-step and an overall verdict, return exit code 0
      (Verified OK) / 1 (TAMPERED)
- [x] `--gui`: open a Tkinter window wrapping `gui/replay_view.py::ReplayView`
      only after the headless verdict has already printed
- [x] Integration test: real smoke match -> `report_writer.py` writes
      `log_<game_uid>.json` -> `run_replay` end-to-end, both a clean log
      (`Verified OK`) and a deliberately tampered copy (`TAMPERED`)

## Gap 2 — gatekeeper config-key mismatch + ungated LLM calls (rules 28/29)
- [x] `sdk.py::_build_runtime`: fix the gatekeeper's config keys from the
      nonexistent `rate_limits.*` to the real, shared `rate_limiter_gatekeeper.*`
      schema (`requests_per_minute`, `concurrent_requests`, `retry_backoff_sec`,
      `max_retries`, `queue_depth`) already present in `config/thief/game.json`
- [x] Thread `max_retries`/`retry_backoff_sec` into `ApiGatekeeper`'s
      constructor instead of relying on its defaults coincidentally matching
- [x] `strategy/trash_talk.py`: route `_call_llm_bounded`'s LLM call through
      `ApiGatekeeper.execute`, the same way `report_writer.py` already
      routes the Gmail call
- [x] Test: `ApiGatekeeper` built from a real `config/thief/game.json`
      actually reflects `requests_per_minute=30`/`concurrent_requests=2`/etc.,
      not silently-mismatched defaults

## Lower priority — native config-hash parity (rule 11)
- [x] `domain/negotiation.py::Negotiation`: thread `shared_config_path`
      through `signed`/`verify_peer`, add a `config_sha256` wire field
      computed via the same raw-file-bytes SHA-256 algorithm as
      `interop/cop_wire.py::hash_config_file`, verified alongside the
      existing term-by-term check
- [x] Test: two config files with identical negotiated term values but
      different formatting/whitespace now fail native verification

## Cloud-readiness runbook (rule 10)
- [x] Add `config/thief/game_cop_remote.toml.example` (documented,
      non-local template — `opponent_url`/`my_port` placeholders)
- [x] Add a short "going live" runbook (README section or new doc):
      install ngrok, run it, set `opponent_url`/`my_port`, confirm
      `config/thief/game.json` is byte-identical to the Cop side's copy via
      `sha256sum` on both machines (rule 11) before connecting, confirm
      `token.json` exists and is deliberately excluded from any submission
      archive (in addition to already being `.gitignore`d)

**Deliberately not built:** tunnel automation (a `tools/tunnel.py`
equivalent, a `pyngrok` dependency, a `--tunnel` flag) — reasoned decision
this stage, matching `PRD_5_cloud_tunnel.md`'s own already-documented
design (operator runs the tunnel manually). Confirmed still correct: the
server already binds `0.0.0.0` (`infra/server_lifecycle.py`,
`infra/mcp_server.py::build_server`), so a manually-run tunnel already
reaches it — not an oversight, not blocking.

**Found during implementation, not anticipated in the PRD:**
- `infra/mcp_server.py`'s `negotiate` FastMCP tool has a fixed parameter
  signature schema-validated on every call — adding `config_sha256` to
  `Negotiation.signed()`'s payload without adding a matching (optional)
  parameter here broke every real negotiate call, not just the ones using
  the new field. Fixed alongside the `domain/negotiation.py` change.
- `config/thief/game.toml`'s `[rate_limits]` section wasn't simply reading
  the wrong key — it was a real, deliberate Stage-7-era design (`PLAN.md`:
  "purely local tuning nobody needs to negotiate") that predates Stage 9
  adding the *shared*, negotiated `rate_limiter_gatekeeper` block to
  `game.json` for exactly these numbers. `sdk.py` was never updated after
  that later addition. Resolved by making `rate_limiter_gatekeeper.*` (the
  shared, book-mandated values) authoritative for the token bucket/retry/
  queue-depth numbers, while keeping `[rate_limits]` for the two
  DOS-detector thresholds that still have no shared-schema equivalent.
- `strategy/trash_talk.py`'s LLM path turned out to be fully dead code in
  the real runtime — `peer/runtime_setup.py::build_game_components` always
  passes `llm_provider=None`. The gatekeeper-routing fix was still made
  (and the `gatekeeper` param threaded through `runtime_setup.py`/
  `runtime.py`) so the routing gap doesn't have to be rediscovered whenever
  a real LLM provider eventually gets wired in — that wiring itself remains
  out of scope here.

**Status:** done. All checklist items implemented and tested
(`uv run pytest --cov=thief_peer`: 97.00% coverage, full suite green;
`uv run ruff check .`: clean).
