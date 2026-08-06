# TODO — Stage 5: Public URL + Tunnel Reachability

See `PRD_5_cloud_tunnel.md` for full rationale. Book: Ch.2.
PRD milestone: "Connects to a remote Cop peer over a real tunnel, session updates mutually."

- [ ] Private TOML: `network.public_url`, `network.opponent_url` (now a
      public URL, not localhost), `network.retry_backoff_sec` /
      `network.max_retries` (never in shared `game.json`)
- [ ] `infra/mcp_client.py`: connect-with-retry/linear-backoff against a
      non-localhost `opponent_url`, all timings from config
- [ ] `infra/mcp_client.py`: `DeadlineExceededError` distinct from a plain
      connection failure — bounds the whole call including retries
- [ ] Clear operator-facing error on unreachable tunnel (no silent crash/hang)
- [ ] `shared/watchdog.py` (**new module**, see `PRD_5` §2.3 / `PLAN.md`
      addendum): `watchdog_check()`, `persist_state()`, `controlled_shutdown()`
- [ ] Manual/integration run: full scripted match across two independent
      processes reachable only via a public URL

**Done when:** this Thief peer plays a full match against a second independent
process reachable only through a public tunnel URL — no localhost shortcut —
matching the "two students over the internet" scenario.

**Status:** not started
