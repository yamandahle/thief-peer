# TODO — Stage 5: Public URL + Tunnel Reachability

See `PRD_5_cloud_tunnel.md` for full rationale. Book: Ch.2.
PRD milestone: "Connects to a remote Cop peer over a real tunnel, session updates mutually."

- [x] Private TOML: `network.public_url`, `network.opponent_url` (now a
      public URL, not localhost), `network.retry_backoff_sec` /
      `network.max_retries` (never in shared `game.json`) — documented as
      `McpTransport` constructor parameters; wiring `ThiefSdk`/`cli.py` to
      actually read them is deferred to `PeerRuntime` (not built until a
      later stage), matching `smoke_test()`'s already-documented Stage-2-only
      scope
- [x] `infra/mcp_client.py`: connect-with-retry/linear-backoff against a
      non-localhost `opponent_url`, all timings from config
- [x] `infra/mcp_client.py`: `DeadlineExceededError` distinct from a plain
      connection failure — bounds the whole call including retries
- [x] Clear operator-facing error on unreachable tunnel (no silent crash/hang)
      — `TransportError` names the URL and attempt count, never a bare
      socket traceback
- [x] `shared/watchdog.py` (**new module**, see `PRD_5` §2.3 / `PLAN.md`
      addendum — already present in `PLAN.md`'s module list, that "open
      item" was stale, corrected in `PRD_5`): `watchdog_check()`,
      `persist_state()`, `controlled_shutdown()`
- [ ] **Manual/integration run (operator action, not automatable):** full
      scripted match across two independent processes reachable only via a
      public tunnel URL. This requires installing ngrok/Localtonet and
      running two real processes against each other's public URLs — the
      book explicitly frames tunnel startup as an operator action, not
      something the peer process automates (`PRD_5` §4). Not performed as
      part of this stage's automated implementation; the retry/backoff/
      deadline logic that makes such a run resilient is built and
      unit-tested, but the actual over-the-internet run itself is still
      outstanding and needs to be done by hand when convenient.

**Done when:** this Thief peer plays a full match against a second independent
process reachable only through a public tunnel URL — no localhost shortcut —
matching the "two students over the internet" scenario.

**Milestone met (automated portion):** ✅ `McpTransport.call()` has real
linear-backoff retry (`retry_backoff_sec * attempt`, up to `max_retries`)
bounded by an overall `response_timeout_sec` deadline, raising a distinct
`DeadlineExceededError` on timeout and an operator-facing `TransportError`
(names the URL + attempt count) after retries are exhausted — all
config-driven, no hardcoded values. `shared/watchdog.py` adds the
independent whole-system heartbeat check the book cross-references from
Ch.2.4.1. 128 unit+integration tests pass, 97.6% coverage, ruff clean, all
files under 150 lines.

**Not yet done — manual step outstanding:** the actual "two independent
processes over a real public tunnel" run (see checklist above). The
milestone's *automated* prerequisites are complete; the operator-run
verification itself has not been performed.

**Status:** automated portion done; manual tunnel run outstanding
