# TODO — Stage 2: Basic FastMCP Infra (localhost)

See `PRD_2_mcp_infra.md` for full rationale. Book: Ch.2.
PRD milestone: "Raw message from a peer received and decoded correctly on localhost."

- [x] `infra/mcp_server.py`: FastMCP app + a raw ping/echo tool
- [x] `infra/mcp_client.py`: `McpTransport` minimal send/poll against a localhost URL
- [x] `shared/config.py`: extend with `network.my_port` / `network.opponent_url` (private only)
- [x] Port-in-use fail-fast with an actionable error message
- [x] `sdk/sdk.py`: introduce `ThiefSdk` skeleton (single entry point), even
      before the full runtime exists
- [x] `cli.py` + `main.py`: minimal presentation-only smoke command delegating
      to `ThiefSdk`
- [x] Integration test: two in-process FastMCP servers on two localhost ports
      exchange one raw JSON message

**Done when:** two separate processes, each running its own FastMCP server+
client with no shared state, exchange a raw JSON message over localhost —
proves the peer-to-peer topology (no central server).

**Milestone met:** ✅ `tests/integration/test_mcp_roundtrip.py` starts a real
FastMCP server (its own thread, its own OS-level TCP socket on a free port)
and drives it with a real `McpTransport` client over an actual localhost
connection — no mocking. 58 unit+integration tests pass, `uv run ruff check`
clean, all new/changed files under 150 lines. `TransportError` (new
exception type, distinct from `SimulationError`) covers both the port-in-use
and unreachable-opponent failure paths.

**Status:** done
