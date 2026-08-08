# TODO — Stage 8: PeerRuntime + the Live-Match MCP Tools

See `PRD_8_peer_runtime.md` for full rationale. Book: Ch.5 §5.3.2 / Ch.8.
PRD milestone: "`run --group-name ... --config ...` drives a full match
against a real opponent from handshake through Step-0, every round's
commit/reveal, mutual audit, and a Gmail report — no manual step in between."

Not part of the original 7-stage plan — a genuine gap found after Stage 7
shipped (`PeerRuntime` was named throughout `PLAN.md`'s architecture but no
stage's TODO ever claimed it as a task; see `README.md`'s "Known gap" note
and `PRD_8` §2.1).

- [x] `domain/protocol.py`: `build_commit_message` / `build_reveal_message`
      (never a `nonce` or `position` key) / `build_audit_payload` — the
      literal two-separate-messages shape from the book's Figure 6, not the
      single bundled `TurnMessage` `PLAN.md` §5 previously (incorrectly)
      described
- [x] `peer/turn_fsm.py`: `TurnFsm` with the book's literal transition table
      (Ch.8 p.63, extracted via `pdftotext`, not paraphrased) — illegal
      transitions raise `SimulationError` immediately
- [x] `peer/round_exchange.py`: thread-safe mailbox bridging the MCP server
      thread and the main loop thread — `wait_for_commit`/`wait_for_reveal`
      raise `DeadlineExceededError` on timeout, mapped to `TECHNICAL_LOSS`
- [x] `peer/turn_sender.py`: `send_commit`/`send_reveal` — builds
      `protocol.py` payloads, calls the new MCP tools
- [x] `infra/mcp_server.py`: `build_server(port, context)` gains `negotiate`,
      `receive_control`, `commit_move`, `reveal_move` tools, each a one-line
      delegation to `context.handle_*` — every existing `build_server(port)`
      caller (smoke test + 4 integration tests) updated with a context arg
- [x] `peer/runtime.py`: `PeerRuntime` — wires `handshake.run_handshake` →
      the round loop (§2.5) → `submit_audit` → `report_writer.write_and_send`,
      all reused unmodified; `.view()` for the GUI
- [x] `sdk/sdk.py`: `ThiefSdk.run(group_name)`; `cli.py`: `run` subcommand
      (parsing only, `smoke-test` unchanged)
- [x] Tests: FSM transition-table test (every book edge + every rejected
      non-edge); protocol structural tests (no nonce/position leak);
      `RoundExchange` cross-thread test; `PeerRuntime` unit test against a
      stub transport (matching `test_handshake.py`'s `_StubPeerTransport`
      pattern); **two-real-`PeerRuntime`-instances** integration test
      driving a full short match to completion over real localhost MCP
      servers, asserting clean audits on both sides and matching `game_uid`s
      in both sides' report output

**Also fixed along the way (not originally scoped, but required):** two real
bugs surfaced only once two independent `PeerRuntime`s actually ran against
each other over real sockets, rather than one hand-wired smoke test:
1. `domain/game_ids.py`'s `derive_game_id` is deliberately order-sensitive
   (Stage 6, tested); calling it as `derive_game_id(my_group, their_group)`
   from each side therefore produced two *different* game_ids for the same
   match. Fixed in `peer/match_end.py` by sorting the two names before
   deriving the id — `derive_game_id` itself is unchanged.
2. `report_writer.write_and_send`'s `league_counter` parameter silently
   defaulted to a path relative to the process's current working directory
   whenever a caller omitted it — `peer/match_end.py` was the first caller
   to omit it, and running two real peers wrote a real, repo-directory
   `results/league_counter.json` as a result. Fixed by always constructing
   `LeagueCounter` from the match's own `results_dir`.

**Done when:** two independent `PeerRuntime` processes, each started via
`cli.py run`, play a full match to completion over MCP with no manual step
beyond starting each process — handshake, every round's commit/reveal, the
end-of-match mutual audit, and each side's Gmail report all happen
automatically.

**Milestone met:** ✅ `tests/integration/test_live_match.py` — two real
`PeerRuntime` instances, each with its own real FastMCP server and outbound
`McpTransport`, play a full match to completion over live localhost
sockets: handshake, every round's commit/reveal, a *genuinely mutual*
audit on both sides (each peer actively pulls and verifies the other's
revealed log via `get_revealed_records`, not just submits itself), and
matching `game_uid`s in both sides' report output. Capture-by-barrier
detection (rules 21/22/46) also closed post-shipment — see the PRD's two
addenda for both fixes. 363 unit+integration tests passing, 96.8%
coverage, ruff clean, every new/changed file at or under 150 lines.

**Status:** done
