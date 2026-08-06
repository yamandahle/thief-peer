# TODO — Stage 2: Basic FastMCP Infra (localhost)

See `PRD_2_mcp_infra.md` for full rationale. Book: Ch.2.
PRD milestone: "Raw message from a peer received and decoded correctly on localhost."

- [ ] `infra/mcp_server.py`: FastMCP app + a raw ping/echo tool
- [ ] `infra/mcp_client.py`: `McpTransport` minimal send/poll against a localhost URL
- [ ] `shared/config.py`: extend with `network.my_port` / `network.opponent_url` (private only)
- [ ] Port-in-use fail-fast with an actionable error message
- [ ] `sdk/sdk.py`: introduce `ThiefSdk` skeleton (single entry point), even
      before the full runtime exists
- [ ] `cli.py` + `main.py`: minimal presentation-only smoke command delegating
      to `ThiefSdk`
- [ ] Integration test: two in-process FastMCP servers on two localhost ports
      exchange one raw JSON message

**Done when:** two separate processes, each running its own FastMCP server+
client with no shared state, exchange a raw JSON message over localhost —
proves the peer-to-peer topology (no central server).

**Status:** not started
