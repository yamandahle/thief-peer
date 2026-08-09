# PRD 10 — Cop-Parity Audit + Cloud-Readiness Hardening

Not part of the original 7-stage plan, nor Stage 9's interop adapter — the
Cop team's own AI assistant sent a message to this team claiming 6
"advanced engineering extensions" in `finalProject cop` that go beyond the
book's basic requirements, asking for the same level of protection to be
wired into this repo. This stage is the independently-verified answer to
that claim (each of the 6 checked against Cop's actual cloned source and
cross-checked against this repo's real code, not accepted at face value),
plus a companion cloud-readiness audit against rule 10.

## 1. Why this exists

Trusting a self-description of "what my code does" without reading it is
exactly the failure mode this whole project's Commit-Reveal discipline
exists to prevent between two mutually-distrusting peers — the same
skepticism applies to a claim about a teammate's own code. Every one of the
6 claims below was checked file-by-file against her actual source before
being treated as true. Headline result: **4 of 6 already have full parity
in this repo, independently arrived at**; **2 are real, precise gaps**, and
a separate audit of rule 10 (public reachability) found two more concrete,
low-risk follow-ups.

## 2. Verified at parity — no action needed

1. **Scent-model SHA-256 lock (ch.4.5, rule 23 [FATAL]).** `domain/scent_lock.py::scent_lock_hash`
   matches her `integrity/scent_model_lock.py::compute_scent_model_hash`
   byte-for-byte (same formula-shape string, same synthetic 9×9 board,
   same `.10f` precision, same canonical-JSON discipline — both sides
   independently compute the same hash for the book's default parameters).
   Wired into both the native `domain/negotiation.py::Negotiation` and
   `interop/cop_handshake.py`, verified before turn 1 either way.
2. **Byte-identical config check, cop_v1 path (rule 11 [FATAL]).**
   `interop/cop_wire.py::hash_config_file` is genuine raw-file-bytes
   SHA-256, matching her `integrity/step0.py::hash_config_file` exactly,
   and it's *enforced* (blocking, raises `ConfigError`) in
   `interop/cop_handshake.py`, not just computed and left unchecked.
3. **Live belief-heatmap GUI (rules 8/9).** `gui/board_view.py::_heat_color`
   + `BoardView.render` draws a genuine per-cell color-coded heatmap of
   `domain/belief.py::BeliefGrid`, the same technique as her
   `observability/live_gui.py`. Local-truth-only is enforced the same way
   on both sides: her `render_state` signature and this repo's
   `gui/window.py::PeerView` dataclass both structurally exclude an
   opponent-position field — there is no code path that could leak it.
4. **Zero-token template hint provider (rule 25).**
   `strategy/talk_providers.py::TemplateProvider` is the default/fallback
   hint generator in `strategy/trash_talk.py::TrashTalk.generate_hint`
   (LLM use is optional, throttled to `every_n_steps`, and always falls
   back to the template on `None`/timeout/error) — the same architecture
   as her `tools/hint_providers.py::TemplateHintProvider` alongside her
   optional LLM-backed providers.

## 3. Gap 1 — the replay-and-verify viewer is never actually reachable (rule 20, [FATAL])

`gui/replay_view.py::replay()` / `verify_step()` / `ReplayView` are correct
and already unit-tested (`tests/unit/test_replay_view.py`) — they reuse
`domain/crypto.py::CommitReveal.verify`, the exact same primitive every
other layer of this repo already trusts, never a separate/duplicated
verification routine. The problem: **nothing outside that one module ever
calls them.** `cli.py` has exactly three subcommands (`smoke-test`, `run`,
`auth-gmail`) — no `replay` subcommand exists, and `sdk.py`/`__main__.py`
never reference `ReplayView`. This is `docs/PRD.md` §2.2's own still-open
acceptance checkbox: *"Live GUI + Replay App both show 'Verified OK'"* —
half of that pair has never been wired to anything a grader (or this team)
could actually run.

**The good news found while scoping this:** no new persistence format is
needed. `report/report_writer.py::write_and_send` already writes
`results/log_<game_uid>.json` via `report/artifacts.py::build_log(records,
audit)`, and that `records` array is already exactly the shape
`verify_step()`/`replay()` expect — `{"payload": {..., "nonce": ...},
"commit": ...}` per entry, sealed by the same `peer/sealing.py::sealed_step_record`
every turn already uses. This is a pure CLI/SDK wiring gap, not a missing
log writer.

**Fix shape**, mirroring her own `cli_replay.py`'s headless-first design
(a real grader's situation is "just this log file, maybe no display" —
the verdict should never depend on a GUI actually opening):
- `cli.py`: add a `replay` subparser (`--log <path>`, `--gui`).
- `sdk.py::run_replay(log_path, gui=False) -> int`: load the JSON file,
  read `data["records"]`, run `verify_step()` per entry, print a per-step
  and an overall verdict, return a correct process exit code (0 = Verified
  OK, 1 = TAMPERED — no ambiguous middle state, matching rule 20's own "no
  appeal" framing). Only if `--gui` is passed, additionally open a Tkinter
  window wrapping `ReplayView` — after the headless verdict already
  printed, never the only way to get an answer.

## 4. Gap 2 — the Gatekeeper silently reads a config key that doesn't exist

`sdk/sdk.py::_build_runtime` constructs `ApiGatekeeper`/`TokenBucket`/
`DosDetector` from `config.get("rate_limits.token_bucket_capacity", 5)`,
`"rate_limits.token_bucket_refill_rate"`, `"rate_limits.dos_max_calls"`,
`"rate_limits.dos_window_seconds"`, `"rate_limits.queue_max_depth"` — but
`config/thief/game.json`'s real, shared schema is `rate_limiter_gatekeeper.*`
(`requests_per_minute: 30, concurrent_requests: 2, retry_backoff_sec: 5,
max_retries: 3, queue_depth: 100` — the identical Appendix-F numbers her
own `config/shared/config_dev_g01.json` carries). Because the key path is
wrong, `ConfigManager.get()` silently falls through to the hardcoded
defaults instead of ever raising — the book-mandated numbers sit unused in
the config file while the real runtime quietly uses different ones
(capacity 5 / refill 1.0 per sec ≈ 60 req/min, not the negotiated 30).
Per this project's own precedence rule (`RULES.md`'s own citation of the
book): *"the parameter table is the sole source of truth for every numeric
value"* — a silent divergence here is exactly the class of bug that rule
exists to prevent. Separately, `max_retries`/`retry_backoff_sec` are never
read into `ApiGatekeeper` at all today; its constructor defaults happen to
coincidentally match, which is luck, not wiring.

Also found: **LLM calls bypass the gatekeeper entirely.**
`strategy/trash_talk.py::TrashTalk._call_llm_bounded` calls
`self._llm.generate` directly through a `ThreadPoolExecutor`, never through
`ApiGatekeeper.execute`. `infra/llm_provider.py`'s own module docstring
already self-documents this as a known, deferred gap ("real network calls
will be routed through `shared/gatekeeper.py` once Stage 7 builds it --
until then ollama calls out directly") — Stage 7 built the gatekeeper, but
this specific wiring was never finished. Email is correctly gated
(`report/report_writer.py:85`); LLM never was.

**Fix shape:**
- `sdk.py::_build_runtime`: read from `rate_limiter_gatekeeper.*` (the real
  schema), and thread `max_retries`/`retry_backoff_sec` into
  `ApiGatekeeper`'s constructor instead of relying on its defaults.
- `strategy/trash_talk.py`: route the bounded LLM call through
  `ApiGatekeeper.execute` the same way `report_writer.py` already routes
  the Gmail call — same rate limiting, same DOS protection, same retry
  discipline, one gatekeeper for every external call this peer makes.

## 5. Lower priority — native protocol's config check is weaker than cop_v1's

`domain/negotiation.py::Negotiation.verify_peer` only compares negotiated
*term values* field-by-field (`CANONICAL_TERM_KEYS`); there is no raw
byte-identical file hash on the native path, unlike `interop/cop_wire.py::hash_config_file`
on the cop_v1 path (already at parity, §2 above) and unlike her own
`integrity/step0.py::hash_config_file`. Two config files that differ in
formatting/whitespace but carry identical negotiated values would currently
pass native verification even though they are not byte-identical, which is
what rule 11 literally requires.

Not an active bug today — no other opponent currently speaks this repo's
"native" wire vocabulary (confirmed by `grep`: it only appears in this
repo's own self-tests) — but worth closing for defense-in-depth before any
future native-speaking league opponent exists.

**Fix shape:** thread `shared_config_path` into `Negotiation.signed`/
`verify_peer` (the same path `PeerRuntime.shared_config_path` already
carries for the cop_v1 path), add a `config_sha256` wire field computed via
the same `hash_config_file` algorithm, verified alongside the existing
term-by-term check.

## 6. Cloud-readiness runbook (rule 10)

**Confirmed already correct:** the server binds `0.0.0.0`
(`infra/server_lifecycle.py::run_server_in_background`,
`infra/mcp_server.py::build_server`'s own default) — a tunnel pointed at
this process would already reach it. Not a blocker.

**Confirmed, deliberate design — not changing it.** This repo has no
tunnel-automation module (no equivalent to her `tools/tunnel.py`/`--tunnel`
flag) by design, already reasoned through in `docs/PRD_5_cloud_tunnel.md`
§4: the operator installs and runs ngrok/Localtonet by hand, then pastes
the resulting URL into `game.toml`'s `network.opponent_url`. Revisited this
stage and **kept as-is** — adding tunnel automation now would reopen an
already-closed, reasoned decision for marginal benefit, and the retry/
deadline/watchdog machinery a real tunnel connection needs is already built
per `PRD_5`.

**What's actually missing, and worth closing:**
- No non-local config template exists anywhere in `config/` — all three
  checked-in TOML files hardcode `opponent_url` to `127.0.0.1`. A real
  match currently requires hand-editing `game.toml` in place from a
  description in a code comment, with no ready-made starting point.
- `token.json` (the completed Gmail OAuth token) exists on disk, is
  correctly listed in `.gitignore`, and has never been committed
  (`git log --all -- token.json` is empty — no rule 39/40 leak). It's
  still a live, unrotated credential sitting in the working directory,
  which is a submission-hygiene risk distinct from a git-history leak: a
  submission archive built by zipping the whole working directory rather
  than `git archive`ing a clean tag would include it.

**Fix shape:**
- Add `config/thief/game_cop_remote.toml.example` — the same fields as the
  existing local-test TOMLs, with `opponent_url`/`my_port` placeholders and
  a comment pointing at the manual steps below, so a real match starts from
  a template instead of a prose description.
- Add a short "going live" runbook (a README section or a small new doc):
  install ngrok, run it, set `opponent_url`/`my_port`, confirm
  `config/thief/game.json` is byte-identical to the Cop side's copy via
  `sha256sum` on both machines before connecting (rule 11), confirm
  `token.json` exists and is deliberately excluded from any submission
  archive (in addition to already being gitignored).

## 7. Deliberately not built / out of scope

- **Tunnel automation** (a `tools/tunnel.py` equivalent, a `pyngrok`
  dependency, a `--tunnel` flag) — a reasoned decision this stage, not an
  oversight. See §6 and `docs/PRD_5_cloud_tunnel.md` §4 for the full
  reasoning; revisit only if the manual-operator model proves impractical
  in a real league match.
- Making the native protocol's per-turn Commit-Reveal envelope match her
  7-field shape is **already done** (Stage 9's follow-up commit,
  `de963c4`) — out of scope for this stage, not re-litigated here.

## Verification (for the implementation stage that follows this PRD)

- `uv run pytest --cov=thief_peer --cov-report=term-missing` and
  `uv run ruff check .` clean after every fix in `TODO_10_cop_parity_hardening.md`.
- A real integration test: play a short scripted/smoke match, write its log
  via `report_writer.py`, then run the new `replay` CLI path against the
  resulting file end-to-end — once against a clean log (`Verified OK`) and
  once against a deliberately tampered copy (`TAMPERED`).
- After the gatekeeper fix: a test asserting `ApiGatekeeper` is actually
  constructed with `requests_per_minute=30`/`concurrent_requests=2`/etc.
  from a real `config/thief/game.json`, not silently falling back to
  mismatched defaults.
