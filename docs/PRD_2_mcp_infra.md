# PRD — Stage 2: Basic FastMCP Infrastructure (localhost)

**Status:** DRAFT — pending approval before implementation
**Stage:** 2 of 7 (see `TODO.md`)
**Book reference:** Chapter 2 — "P2P Architecture and FastMCP Infrastructure"
**Modules covered:** `infra/mcp_server.py`, `infra/mcp_client.py`,
`shared/config.py` (extended), `sdk/sdk.py` (skeleton), `cli.py`, `main.py`

---

## 1. Purpose & Theoretical Background

This stage builds the communication substrate that makes the "no central
server" architecture concrete (book Ch.2). Instead of a hub-and-spoke model
with a judge, each peer is **simultaneously an MCP server and an MCP client**:
it exposes tools the opponent calls, and it calls tools the opponent exposes.
There is no third process brokering the match.

🎯 **MCP is the mandatory transport** — not a stylistic choice. Substituting a
plain REST API or raw sockets, even if functionally equivalent, risks losing
points because the book explicitly requires this specific protocol
(`FastMCP`, the Python library) as the interoperability layer between
independently-built peers.

This stage deliberately stays on `localhost` — public reachability over a
tunnel is Stage 5. The goal here is proving the *topology* works (two
processes, no shared state, exchanging messages) before adding network
complexity, timeouts/retries, or real game content on top of it.

---

## 2. Detailed Description

### 2.1 Dual role per peer
Each Thief process runs:
- **A FastMCP server** (`infra/mcp_server.py`) — exposes tools the Cop peer's
  client calls (e.g., `receive_turn`). Owns resource management and
  async response handling.
- **A FastMCP client** (`infra/mcp_client.py`, wrapped as `McpTransport`) —
  calls tools exposed by the Cop's server, at the Cop's URL.

These are two distinct objects inside one process — not two processes, and
not shared with any Cop-side code (the Cop peer is a wholly separate
repository; this Thief peer never imports anything from it).

### 2.2 Never trust incoming data blindly
Every exposed tool must validate its input before acting on it (book Ch.2
grading flag) — even at this stage, before cryptographic sealing exists
(Stage 6), the server should reject malformed/incomplete messages rather than
assume well-formed input. This stage's tools are intentionally minimal
(ping/echo), but the validate-before-trust pattern is established here so
later stages (real `receive_turn`, `submit_audit`) inherit it rather than
retrofitting it.

### 2.3 Config split applies here too
- `network.my_port` and `network.opponent_url` are **private** settings
  (this peer's own network configuration) — they belong in
  `config/thief/game.toml`, never in the shared, signed `game.json` (per
  `PLAN.md` ADR-5). The opponent's URL is specific to *this* match/session,
  not a term both sides must cryptographically agree on.

### 2.4 `ThiefSdk` skeleton (SDK mandate)
Per the engineering standard, all business logic must sit behind one SDK
entry point. This stage introduces `sdk/sdk.py`'s `ThiefSdk` class even though
it does very little yet (Stage 2 doesn't have a real game loop) — establishing
the call boundary early (`cli.py` → `ThiefSdk` → everything else) prevents
logic from accidentally creeping into `cli.py` in later stages, which would be
harder to refactor out once the CLI has grown.

---

## 3. Requirements (Input / Output / Behavior)

### `infra/mcp_server.py`
| Item | Behavior |
|---|---|
| `build_server(port: int) -> FastMCP` | constructs a FastMCP app bound to `0.0.0.0:<port>` (bind-all so a later tunnel can reach it; still only *tested* via localhost this stage) |
| `@mcp.tool def ping(payload: dict) -> dict` | validates `payload` has expected keys; echoes back `{"pong": True, "received": payload}`; this is the Stage-2 stand-in for the real `receive_turn` tool that arrives in Stage 4/6 |
| Startup | must fail fast with an actionable error (not a bare traceback) if the configured port is already in use — check *before* attempting to bind |

### `infra/mcp_client.py` — class `McpTransport`
| Method | Input | Output | Behavior |
|---|---|---|---|
| `__init__(opponent_url: str)` | opponent's base URL, from private config | — | stores URL, does not connect yet (lazy) |
| `call(tool_name: str, payload: dict) -> dict` | tool name + JSON-serializable payload | the tool's JSON response | opens an MCP client connection, invokes the named tool, returns the result; raises a clear, typed error (not a bare exception) on connection failure |

### `shared/config.py` (extension over Stage 1's v0)
- Adds `network.my_port` (int) and `network.opponent_url` (str) as **required
  private** keys — `ConfigManager` fails fast (`ConfigError`) if either is
  missing when a networked command is run.
- Still reads `config/thief/game.toml` only at this stage; `game.json`
  (shared) parsing/validation is deferred to Stage 4 when it's actually
  needed for game content, to keep this stage's scope tight.

### `sdk/sdk.py` — class `ThiefSdk` (skeleton)
| Method | Behavior (Stage 2 scope) |
|---|---|
| `__init__(config: ConfigManager)` | stores config, builds nothing eagerly |
| `smoke_test() -> dict` | Stage-2-only diagnostic method: starts the local server, calls `ping` against the configured `opponent_url`, returns the round-trip result — this method is expected to be **deleted** once Stage 3+ introduces the real `run()` method; it exists purely to give this stage a demonstrable, testable end-to-end path |

### `cli.py` / `main.py`
- `main.py`: thin launcher, delegates to `thief_peer.cli:main()`.
- `cli.py`: parses a minimal `smoke-test` subcommand (Stage 2 only), calls
  `ThiefSdk.smoke_test()`, prints the result. **Zero game logic** — this file
  must stay a pure argument-parsing-and-delegation shim for the life of the
  project (SDK mandate), not just at this stage.

---

## 4. Limitations, Constraints, Alternatives Considered

- **Why FastMCP and not raw `asyncio`/sockets/REST:** covered in §1 — this is
  a mandatory-protocol requirement from the book, not a technical judgment
  call. Even though a hand-rolled REST API would be simpler for a ping/echo
  tool, using it here would mean re-doing the networking layer in Stage 4/6
  when it stops being simple — and risks non-compliance with graders checking
  for MCP specifically.
- **Why `ping`/`echo` and not the real `receive_turn` tool yet:** keeps Stage
  2 testable in total isolation from game rules (Stage 1) and crypto (Stage
  6) — proves the transport works before layering content on it. The real
  tool signatures are already fixed in `PLAN.md` §5 (API contracts) so this
  stub doesn't invent a shape that later needs breaking changes.
- **Alternative considered and rejected: skip the `ThiefSdk` skeleton until
  Stage 3.** Rejected because introducing the SDK boundary *after* `cli.py`
  already has direct calls into `infra/` would mean a refactor, not just an
  addition — cheaper to establish the boundary now while there's almost
  nothing behind it.
- **Deferred, not solved here:** connection retry/backoff and timeouts belong
  to Stage 5 (public URL/tunnel reachability), where network unreliability
  actually becomes relevant; a bare `call()` that just fails on the first
  error is acceptable for a localhost-only stage.

---

## 5. Acceptance Criteria & Test Scenarios

- [ ] Two separate OS processes (not threads within one process — this is
      the actual topology the real match will use), each with its own
      `config/thief/game.toml` (or a test-only variant), successfully:
      process A's server receives and correctly echoes a `ping` call from
      process B's client.
- [ ] Starting a server on a port already in use produces a clear,
      actionable error (test by pre-binding the port, then starting the
      server and asserting the specific error type/message — not a bare
      socket exception).
- [ ] `McpTransport.call()` against an unreachable URL raises a typed error,
      not an unhandled exception that crashes the process.
- [ ] `ThiefSdk.smoke_test()` round-trips successfully against a locally-
      started server on the configured port.
- [ ] `cli.py` contains no `if`/business-logic branching beyond argument
      parsing — verified by code review against the SDK mandate, not just
      a test (this is a structural/architectural check).
- [ ] Integration test (`tests/integration/`) spins up both a server and a
      client in-process (or as subprocesses) and asserts the round trip,
      runnable via `uv run pytest tests/integration`.
- [ ] `uv run ruff check` clean; unit-testable pieces (`ConfigManager`
      extension, error types) meet the ≥85% coverage bar — integration
      tests involving real sockets are exempted from the coverage
      percentage per usual pytest-cov conventions but must still exist and pass.

**Stage 2 "Done" milestone (from TODO.md, unchanged here):** two separate
processes, each running its own FastMCP server+client with no shared state,
exchange a raw JSON message over localhost — proves the peer-to-peer topology
(no central server).

---

## Open item carried over
The Stage-1 "stuck = captured" rule ambiguity (see `PRD_1_base_logic.md` §4)
is still unresolved — does not block this stage (no rules logic is touched
here), but must be settled before Stage 6 seals move records into the
audited log.
