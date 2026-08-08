# Architecture Plan — Thief Peer

**Status:** DRAFT — pending approval before TODO.md / per-stage PRDs / code
**Package name:** `thief_peer`
**Companion doc:** `docs/PRD.md` (approved) — this document must not contradict
its scope, acceptance criteria, or milestones.

---

## 1. Module / Directory Layout

```
thief-peer/                                # this repo root (separate from teammate's Cop repo)
├── pyproject.toml                         # uv, ruff (E,F,W,I,N,UP,B,C4,SIM), pytest-cov fail_under=85
├── uv.lock
├── .env-example                           # GMAIL_*, ANTHROPIC_API_KEY dummy placeholders
├── .gitignore                             # .env, credentials.json, token.json, *.key, *.pem, logs/, results/
├── README.md                              # academic report (Ch.9 mandatory sections)
├── src/thief_peer/
│   ├── __init__.py
│   ├── __main__.py                        # `uv run python -m thief_peer ...` -- the sole launcher; a separate repo-root main.py was sketched here originally but never built, and turned out unnecessary once this existed (see PRD_8 addendum 3)
│   ├── cli.py                             # argument parsing ONLY -> calls ThiefSdk, zero logic
│   ├── constants.py                       # Direction(N/S/E/W), MoveType, NONCE_BYTES, protocol strings
│   ├── exceptions.py                      # ConfigError, CryptoError, SimulationError, ProviderError
│   ├── sdk/
│   │   ├── __init__.py
│   │   └── sdk.py                         # ThiefSdk — THE single entry point (run(), replay())
│   ├── domain/                            # pure game logic — no I/O, no LLM, no network
│   │   ├── board.py                       # Board: legal_moves (N/S/E/W/STAY), Manhattan distance
│   │   ├── own_state.py                   # OwnGameState: my position, visited trail, known barriers
│   │   ├── scent.py                       # ScentField: advance() (5x5 kernel + decay, one atomic step), absorb
│   │   ├── belief.py                      # BeliefGrid: Bayesian update from scent+hints, diffuse()
│   │   ├── rules.py                       # capture-on-barrier / no-legal-move / survival checks
│   │   ├── crypto.py                      # canonical_json, CommitReveal, audit_records() — see §5
│   │   ├── negotiation.py                 # shared-config signature exchange (reuses CommitReveal)
│   │   ├── protocol.py                    # build_commit_message/build_reveal_message/build_audit_payload (dict builders, not dataclasses -- Stage 8 correction, matches sealing.py/negotiation.py's existing convention)
│   │   └── game_ids.py                    # deterministic game_id / game_uid derivation
│   ├── strategy/                          # THE graded differentiator — pure Python, NEVER the LLM
│   │   ├── brain_base.py                  # BrainBase, Decision dataclass, resolve_brain() factory
│   │   ├── fleeing_brain.py               # ThiefBrain(BrainBase): maximize distance from belief peak
│   │   ├── trash_talk.py                  # hint+verdict orchestration, throttling, fallback-to-template
│   │   └── talk_providers.py              # template / ollama / claude_api / claude_cli adapters
│   ├── peer/                              # the turn-taking protocol — ONE peer, no shared process
│   │   ├── runtime.py                     # PeerRuntime: negotiate -> turn loop -> audit (Stage 8)
│   │   ├── runtime_setup.py               # game-component construction, split out of runtime.py (Stage 8)
│   │   ├── runtime_context.py             # infra/mcp_server.py context handlers, split out of runtime.py (Stage 8)
│   │   ├── round_loop.py                  # one commit/reveal round, split out of runtime.py (Stage 8)
│   │   ├── round_exchange.py              # thread-safe mailbox bridging the MCP server thread and the main loop (Stage 8)
│   │   ├── match_end.py                   # end-of-match mutual audit + report, split out of runtime.py (Stage 8)
│   │   ├── heartbeat_monitor.py           # rule-7 watchdog's heartbeat producer + background checker (post-Stage-8 fix)
│   │   ├── turn_fsm.py                    # explicit turn state machine + illegal-transition rejection (book's literal table, Stage 8)
│   │   ├── turn_handler.py                # belief+brain decision, applies the move locally (Stage 3/4)
│   │   ├── turn_sender.py                 # build commit/reveal messages -> send (Stage 8)
│   │   ├── sealing.py                     # payload builders, REQUIRED_TERMS fail-fast validation
│   │   └── handshake.py                   # negotiate + Step-0 declaration exchange before move 1
│   │       # (summary.py was sketched here originally but never built --
│   │       # PeerRuntime.view() (for the GUI) and the finalize_match() report
│   │       # payload ended up covering that need directly, no separate module
│   │       # required; removed from this diagram rather than backfilled)
│   ├── infra/                             # adapters to the outside world
│   │   ├── mcp_server.py                  # FastMCP tool routing: negotiate/receive_control/commit_move/reveal_move/submit_audit/get_revealed_records/receive_barrier_declaration/receive_capture_claim, each a one-line context.handle_* delegation
│   │   ├── null_peer_context.py           # NullPeerContext, split out of mcp_server.py (post-Stage-8 fix)
│   │   ├── server_lifecycle.py            # run_server_in_background/wait_until_ready, split out of mcp_server.py (post-Stage-8 fix)
│   │   ├── mcp_client.py                  # McpTransport: calls the Cop's MCP tools
│   │   ├── llm_provider.py                # ollama/claude_api/claude_cli — banter ONLY, never move
│   │   ├── email_sender.py                # Gmail API, structured JSON only, via Gatekeeper -- assumes a valid token already exists
│   │   └── gmail_auth.py                  # one-time OAuth2 bootstrap producing that token (Appendix א §1.5) -- run once by a human, never mid-match
│   ├── report/
│   │   ├── artifact_schemas.py            # schema_version, field docs
│   │   ├── artifacts.py                   # build_declaration / build_config / build_log / build_result
│   │   ├── artifact_helpers.py            # canonical_sha256, filenames
│   │   └── report_writer.py               # assembles + hands result JSON to email_sender
│   ├── shared/                            # cross-cutting infra
│   │   ├── config.py                      # ConfigManager: game.json (shared) + game.toml (private)
│   │   ├── gatekeeper.py                  # ApiGatekeeper.execute() — the ONE doorway for Gmail+LLM
│   │   ├── rate_limiter.py                # token bucket + FIFO queue + DOS/loop detector
│   │   ├── sysinfo.py                     # collect_spec(): OS/CPU/RAM/GPU-VRAM
│   │   ├── watchdog.py                    # watchdog_check(): whole-system heartbeat monitor (PRD_5)
│   │   └── version.py                     # CODE_VERSION
│   └── gui/                               # presentation ONLY — reads PeerRuntime.view(), no logic
│       ├── window.py                      # Tkinter root: turn banner + board canvas + belief heatmap
│       ├── board_view.py                  # renders OWN truth only — never the Cop's real position
│       ├── turn_banner.py                 # renders turn_fsm state
│       ├── replay_view.py                 # steps a saved log, re-verifies hashes live
│       └── live_session.py                # wires a running PeerRuntime to a live PeerWindow (background match thread + Tk .after() polling) -- added after PRD_7/PRD_8 since neither stage actually connected the two
├── config/thief/
│   ├── game.json                          # SHARED, signed, byte-identical with the Cop's copy (real starter file, Stage 8)
│   └── game.toml                          # PRIVATE: port, opponent URL, strategy/LLM selectors, email, Gatekeeper limits (real starter file, Stage 8; rate_limits folded in here rather than a separate rate_limits.json -- ConfigManager only ever merges two files, and these values are purely local tuning nobody needs to negotiate, so a third file added complexity without benefit)
├── data/                                  # match-log fixtures for replay tests
├── results/                               # emitted JSON artifacts per match (gitignored contents)
├── assets/                                # GUI icons, doc images
├── notebooks/                             # optional analysis of match logs
├── docs/
│   ├── PRD.md  PLAN.md  TODO.md
│   └── PRD_1_base_logic.md ... PRD_7_reporting_shell.md
└── tests/
    ├── unit/                              # one file per src module, happy + error path, >=85% cov
    └── integration/                       # two-peer localhost/public-URL full-match tests
```

**Deviation from the mandated generic skeleton, justified:** the guidelines'
flat `services/` folder is replaced with five purpose-built packages (`domain/`,
`strategy/`, `peer/`, `infra/`, `report/`). A P2P turn-based game has clearly
distinct concerns — pure rules, the pluggable decision policy, the turn protocol
state machine, external adapters, and reporting — and collapsing them into one
folder would either blow the 150-line-per-file cap into monster files or produce
an unlabelled pile of same-folder modules. `sdk/` and `shared/` are kept exactly
as mandated.

---

## 2. C4 — System Context

```
                         +----------------------------+
                         |          GitHub             |
                         | (this repo's commit hash;    |
                         |  read, not called, for the   |
                         |  Step-0 declaration)         |
                         +--------------^---------------+
                                        | commit hash read at startup
+---------------+  operates (GUI/CLI) +-+------------------------+  MCP over tunnel   +---------------+
|  Human         |-------------------->|                          |<------------------>|  Cop Peer      |
|  Operator      |                     |       THIEF PEER          |  TurnMessage,       | (separate,     |
|  (this student)|                     |  (this system: MCP        |  Negotiation,       |  independent   |
+---------------+                     |  server + MCP client,     |  AuditPayload,      |  repo/process) |
                                        |  own SDK, own GUI)         |  ControlMessage     +---------------+
                                        +---+------------------+---+
                          optional LLM only  |                  |  structured JSON report
                          (banter text)      |                  |  (via Gatekeeper, OAuth2)
                                             v                  v
                         +---------------------+      +------------------+
                         |  LLM Provider         |      |   Gmail API       |
                         |  (Ollama / Claude API |      | (OAuth2, fixed    |
                         |  / Claude CLI) —       |      |  recipient)       |
                         |  NEVER decides the move|      +------------------+
                         +---------------------+

                         +---------------------+
                         |  Tunnel (ngrok /       |  exposes THIEF PEER's own MCP server
                         |  Localtonet)           |  publicly so the Cop peer (different
                         +---------------------+  machine) can reach it — transparent, no state.
```

**Key point:** there is no box in the middle brokering the match — Thief and Cop
talk directly, peer-to-peer, over MCP; the tunnel is transparent transport only.

---

## 3. C4 — Container / Component (internal call graph)

```
+-------------------------- Presentation (NO logic) --------------------------+
|   cli.py          gui/window.py, board_view.py, turn_banner.py, replay_view.py, live_session.py |
+------------------------------------+-----------------------------------------+
                                     | calls only
                                     v
                          +------------------------+
                          |   sdk/sdk.py            |  <-- SINGLE entry point (SDK mandate)
                          |   class ThiefSdk         |
                          |   .run() / .replay()     |
                          +-----------+-------------+
                                      | builds & drives
                                      v
                          +------------------------+
                          |  peer/runtime.py         |
                          |  PeerRuntime              |
                          +--+----------+---------+--+
              uses           |          |         |            uses
        +---------------------+         |         +---------------------+
        v                               v                               v
+----------------+           +--------------------+          +------------------------+
| peer/turn_fsm.py|           | peer/handshake.py,  |          | peer/turn_handler.py,   |
| (state machine,  |           | peer/sealing.py      |          | peer/turn_sender.py      |
| illegal-         |<----------| (Step-0, commit-      |--------->| (apply/produce           |
| transition        |          | reveal payload builders)|          | TurnMessage)              |
| rejection)         |          +---------+-----------+          +-----+--------------------+
+----------------+                       |                            |
                    +----------------------+                  +---------+---------+
                    v                       v                  v                    v
         +----------------+      +----------------+  +-----------------+  +----------------------+
         | domain/crypto.py|      | domain/          |  | strategy/         |  | domain/board.py,      |
         | domain/          |      | game_ids.py       |  | brain_base.py,    |  | own_state.py, scent.py|
         | negotiation.py   |      |                   |  | fleeing_brain.py, |  | belief.py, rules.py    |
         +----------------+      +----------------+  | trash_talk.py     |  +----------------------+
                                                        +--------+---------+
                                                                 | optional, banter only
                                                                 v
                                                        +----------------------+
                                                        | infra/llm_provider.py |
                                                        |  (via Gatekeeper)       |
                                                        +----------------------+

  PeerRuntime also drives, at the boundary:
        v                                             v
+---------------------+                     +-----------------------------+
| infra/mcp_server.py   |                     | report/artifacts.py,          |
| infra/mcp_client.py    |<-- wire protocol --| report_writer.py               |
| (McpTransport)          |    domain/protocol |---> infra/email_sender.py      |
+---------------------+    .py                +-----------------------------+
                                                (via Gatekeeper)

  Cross-cutting, called from everywhere that needs it, never bypassed:
+-----------------------------------------------------------------------+
| shared/config.py (ConfigManager)   shared/gatekeeper.py (ApiGatekeeper) |
| shared/rate_limiter.py             shared/sysinfo.py  shared/version.py |
+-----------------------------------------------------------------------+
```

**Call-direction rule enforced:** `GUI/CLI -> SDK -> PeerRuntime -> {domain,
strategy, peer/*, infra, report} -> shared`. Nothing in `domain/` or `strategy/`
imports from `infra/`, `gui/`, or `report/`. `infra/llm_provider.py` and
`infra/email_sender.py` are only ever invoked through `shared/gatekeeper.py`.

---

## 4. Architectural Decision Records

**ADR-1 — Strategy is a hard module boundary; the LLM never crosses it into the move.**
*Decision:* `strategy/brain_base.py` exposes exactly one crossing point, the
`Decision` dataclass (`move_type`, `direction`, `hint`, `verdict`, `reasoning`).
`PeerRuntime` never calls an LLM provider directly — only `BrainBase.decide()`
does, and only for the `hint`/`verdict` half of `Decision`, after the move half
is already fixed by pure Python (`_pick_move`).
*Rationale:* the book's Ch.6 hard rule (move is pure Python, never LLM) is a
*scoring* requirement, not a style choice — a leaky boundary would let a slow/
failed LLM stall or bias moves, and would make grading the algorithm vs. the
prompt ambiguous.
*Rejected alternative:* a single combined "reply" object that may or may not
touch an LLM depending on a flag — rejected because it reintroduces exactly the
temptation the book forbids and makes `_pick_move` untestable without stubbing
an LLM.

**ADR-2 — Turn state is an explicit finite-state machine with illegal-transition rejection.**
*Decision:* `peer/turn_fsm.py` owns an explicit state set (`WAITING_FOR_OPPONENT
-> COMPUTING_MOVE -> COMMITTING -> AWAITING_REVEAL -> VERIFYING -> (loop)`,
plus `TECHNICAL_LOSS`) and every transition is checked against an
allow-table; illegal transitions raise immediately rather than silently
overwriting state. (Corrected here, Stage 7: an earlier draft of this ADR
used a different name for the same two states — `WAITING_FOR_COP`/`THINKING`
— than `PRD_7_reporting_shell.md` §2.2 later committed to for the turn
banner's own state names; since `peer/turn_fsm.py` itself was never actually
built before this stage's GUI needed to reference these names, this was
caught and fixed here rather than shipping two docs that disagree. Stage 8
finally builds `peer/turn_fsm.py` itself, and confirmed this state set and
allow-table directly against the book's own literal Python transition table,
Ch.8 p.63 — `PRD_8_peer_runtime.md` §2.4 — rather than continuing to rely on
a paraphrase; the two matched exactly.)
*Rationale:* book Ch.8 — in a fully decentralized 2-peer game there is no
referee to catch a desync; if both peers believe it's their turn (or neither
does), the match deadlocks forever with nothing to intervene. An explicit FSM
with rejection turns a silent hang into a loud, logged, recoverable error.
*Rejected alternative:* ad hoc booleans (`is_my_turn`, `awaiting_reply`)
scattered across `PeerRuntime` — this is exactly what produces the race
conditions the book calls out, and isn't independently unit-testable.

**ADR-3 — Commit-Reveal canonicalization follows the book's exact formula, not the reference repo's variant.**
*Decision:* every sealed payload is hashed **exactly as specified in book Ch.5,
§5.3.1**: the Nonce is one field *inside* a single canonical JSON object
together with State/Move/Intent, then hashed as one blob:
```python
payload = json.dumps({"state": state, "move": move, "intent": intent, "nonce": nonce},
                      sort_keys=True, separators=(",", ":"))
h_commit = hashlib.sha256(payload.encode("utf-8")).hexdigest()
```
*Rationale:* the Cop peer we'll play against — our teammate's, and any other
team's in the league — is a separate, independently-built codebase whose authors
read the same book. At the mutual audit, the opponent must recompute our commit
hash from our revealed `(payload, nonce)` and get an identical digest; the exact
canonicalization algorithm is therefore a cross-team interoperability contract,
not an implementation detail. The lecturer's sample repo actually hashes
`canonical_json(payload_without_nonce) + "|" + nonce` (nonce appended after the
JSON, not embedded in it) — a *different* wire format. Its own README states
"where this repo differs from the book, the book and its binding parameter table
win," so we follow the book's literal formula, which is also what's independently
useful: any other team who read the book carefully (rather than copying the
sample repo's internal choice) will implement the same formula we do.
*Rejected alternative:* mirror the sample repo's `payload|nonce` format instead
— rejected because it risks silent audit failures against Cop peers built by
other teams who followed the book's text instead of the repo's source.

**ADR-4 — One shared `ApiGatekeeper`, not per-module rate limiting.**
*Decision:* `shared/gatekeeper.py` is the only code path allowed to call
`infra/email_sender.py` or `infra/llm_provider.py`; it owns rate limiting (from
`config/thief/game.toml`'s `[rate_limits]` section, never hardcoded — folded
into the private config rather than a separate file, see §1's config/thief/
note), FIFO queuing on overflow,
retry-on-transient-failure, per-call logging, a token-bucket limiter, and a
DOS/infinite-loop detector protecting the Gmail account from a runaway bug.
*Rationale:* book Ch.9 explicitly names a Gatekeeper -> RateLimiter ->
DOS-detector chain as mandatory; the engineering standard separately forbids
scattered ad hoc rate-limit checks. A single chokepoint is the only way to
*guarantee*, not just hope, nothing bypasses it.
*Rejected alternative:* a `@rate_limited` decorator applied per call site —
rejected because decorators duplicate limiter state per call site unless
carefully shared, and it's easy to forget to decorate a new call site later.

**ADR-5 — Config is split by *who must agree*, not by file-format convenience.**
*Decision:* `config/thief/game.json` holds only terms both peers must match
byte-for-byte (board size, scent constants, move set, scoring, survival
threshold) and is verified via the negotiation signature exchange (ADR-6) before
any port opens; `config/thief/game.toml` holds everything purely local (my MCP
port, the Cop's URL, which strategy/LLM class to load, my email settings) and is
never transmitted, hashed, or compared. `ConfigManager` loads both, merges into
one dotted-key namespace (`board.size`, `scent.decay_rate`, ...), and fails fast
(`ConfigError`) at startup if a required shared term is missing — before any
socket opens.
*Rationale:* direct requirement from the engineering standard (no hardcoded
values, secrets/local-config never leak into a signed artifact); fail-fast
before network I/O turns a mid-game crash into an instant local error.
*Rejected alternative:* one config file with per-key `shared: true/false`
metadata — rejected because a single file is trivially easy to accidentally
transmit or commit whole, leaking `opponent_url`/local settings into the signed
artifact; two files/two `.gitignore` rules enforce the boundary at the
filesystem level, not just by convention.

**ADR-6 — The commit-reveal primitive is reused, unmodified, for the pre-game negotiation signature — over a canonical, named wire vocabulary, not our internal config schema.**
*Decision:* `domain/negotiation.py` calls the *same* `CommitReveal.commit_of()`
used for per-step sealing (ADR-3) rather than inventing a separate signing
mechanism: each peer computes `commit_of(my_terms, my_nonce)`, sends
`(terms, nonce, commit)`, and the receiver recomputes the hash and compares.
Critically, `my_terms` is **not** our internal `game.json`/`ConfigManager` dict
serialized as-is — it's built by `negotiation.canonical_terms(config)`, which
projects our locally-named values into a small, fixed, **named** dict
(`CANONICAL_TERM_KEYS`: `grid_size`, `num_agents`, ..., `scent_center_intensity`,
`scent_decay_rate`, `scent_field_size`, `hint_word_limit`, ...) covering exactly
the Mandatory Parameters Table's (Appendix ו) terms. Both peers only need to
agree on *this one documented wire vocabulary* for the `negotiate()` payload —
each is free to name its own internal `game.json`/`ConfigManager` schema
however it likes, same as `TurnMessage`'s field names already need cross-repo
agreement (§5) without constraining either side's internal code. `verify_peer`
compares these named dicts key-by-key, so a mismatch names the exact field that
differs (`"Negotiated terms mismatch on 'grid_size': mine=7 theirs=9"`), not
just "something doesn't match."
*Rationale:* two earlier drafts of this ADR each had a real problem, caught in
turn: the first hashed our own `game.json` dict verbatim, coupling the Cop
repo's negotiation success to using byte-identical *internal* JSON key names —
a self-imposed coupling the book's Appendix ו never asked for (it mandates
values and status, never a field-naming convention). The second draft fixed
that by canonicalizing to a bare positional list ordered by the book's own
table rows — this removed the internal-schema coupling, but lost the ability
to name which field mismatched (a list index isn't self-describing the way a
dict key is), which `verify_peer`'s own acceptance criteria need. The
named-dict design here keeps the first fix's benefit (no internal-schema
coupling) while restoring readable mismatch diagnostics. DRY still holds
throughout: one hashing primitive, reused for both per-step sealing and this
exchange.
*Rejected alternative:* a real asymmetric signature scheme (e.g. Ed25519
keypairs) — disproportionate; the goal is "prove both sides loaded matching
values," which a shared-then-compared commit over a canonical named dict
already achieves without key-distribution complexity the book's crypto scope
doesn't call for.

**ADR-7 — Strategy and LLM-provider choice are pluggable via a dotted-path config selector.**
*Decision:* `strategy/brain_base.py:resolve_brain(config, llm, rng)` reads an
optional `[strategy] thief_class = "my_pkg.module:ClassName"` from the private
TOML, dynamically imports it, asserts it subclasses `BrainBase`, and defaults to
the shipped `ThiefBrain` when unset; `talk_providers.py` resolves its provider
the same way from `[trash_talk] provider = "..."`.
*Rationale:* this is the graded differentiator (PRD §3.5) — it must be swappable
without editing engine files, and "no magic values" forbids hardcoding a
strategy class name inside `PeerRuntime`.
*Rejected alternative:* constructor injection only — kept as a secondary
supported path for tests, but not primary, since the config selector is what
keeps GUI/CLI logic-free while still user-configurable without a code change.

**ADR-8 — True position never crosses the wire or the GUI boundary.**
*Decision:* `domain/protocol.py`'s `TurnMessage` carries `scent_grid` and `hint`,
never a `position` field; `gui/board_view.py` is architecturally unable to
render the Cop's position because `PeerRuntime.view()` (the only thing the GUI
may read) never includes it.
*Rationale:* book Ch.7's hard "must never leak the opponent's real position"
rule; enforcing this only at the GUI-rendering layer would still leave the true
position readable in a wire message or saved log line. Pushing the guarantee
down to "the field literally does not exist in the transmitted/logged struct"
makes partial observability protocol-level and unit-testable (assert
`"position" not in TurnMessage.to_dict()` for our own outgoing message).
*Rejected alternative:* transmit position but instruct the GUI not to draw it —
rejected because it relies on every future GUI/replay code path remembering not
to use a field that's right there in the data.

---

## 5. API / Interface Contracts (Thief repo <-> Cop repo interoperability)

These must be reproduced identically (or at minimum, behavior-identically) in
the independently-built Cop repo — get these wrong and negotiation/audit fails
even with two individually-correct implementations.

**Canonicalization + Commit-Reveal (book Ch.5 §5.3.1, exact formula — see ADR-3):**
```python
payload   = json.dumps({"state": state, "move": move, "intent": intent, "nonce": nonce},
                        sort_keys=True, separators=(",", ":"))
h_commit  = hashlib.sha256(payload.encode("utf-8")).hexdigest()
nonce     = secrets.token_hex(16)          # `secrets` module, NEVER `random`
# verify(): recompute payload from revealed fields, compare via secrets.compare_digest()
```

**`Decision` (internal, strategy -> peer boundary — Thief-repo only, not on the wire):**
| field | type | meaning |
|---|---|---|
| `move_type` | `MOVE` \| `HOLD` | Thief never emits `BARRIER` (Cop-only mechanic) |
| `direction` | `N`\|`S`\|`E`\|`W`\|`None` | `None` iff `move_type == HOLD` |
| `hint` | `str` | <= `hint_max_words` (from shared `game.json`) |
| `verdict` | `"truth"` \| `"lie"` | self-declared honesty of `hint`, sealed & audited |
| `reasoning` | `str` | one-line rationale, sealed into the audit record |
| `response_seconds` | `float` | banter latency, logged |

**Corrected in Stage 8** (`PRD_8_peer_runtime.md` §2.2): the book's Figure 6
(Ch.5 p.51) is explicit that Commit and Reveal are two *separate* messages,
both sides participating at each stage — bundling the hash and the revealed
content into one envelope (as an earlier draft of this section did) would
defeat the "you locked your move before you saw mine" guarantee the whole
mechanism exists for. Replaces the single `TurnMessage` below with two wire
shapes, both built by `domain/protocol.py`'s functions (plain dict builders,
matching `sealing.py`/`negotiation.py`'s existing convention — not
dataclasses):

**`commit_move` payload (MCP tool argument):**
```json
{"step": 7, "sender": "thief", "h_commit": "sha256 hex"}
```
Carries only the hash — never the move, intent, hint, or scent. The book's
"Acknowledge" step is folded into this call's own synchronous MCP response
(`{"ok": true}` = receipt confirmed, lock-in complete) rather than a separate
tool — see `PRD_8` §2.3 for why this doesn't weaken the guarantee.

**`reveal_move` payload (MCP tool argument, sent only after both sides have
committed for this step):**
```json
{
  "step": 7, "sender": "thief",
  "hint": "<natural language, may lie, word-capped>",
  "scent_grid": {"3,4": 0.9, "3,5": 0.7},
  "move": "N", "intent": "truth"
}
```
`move`/`intent` are revealed in the clear now (they were already locked
behind `h_commit` before either side saw the other's); the `nonce` is
**never** included here — withheld until the end-of-match `submit_audit`
exchange (Stage 6, unchanged). No `position` field ever, in either message
(ADR-8).

**MCP tool names/signatures (must match exactly on both peers):**
```
negotiate(message: dict) -> {"terms": dict, "nonce": str, "commit": str}
receive_control(message: dict) -> {"record": dict}   # Step-0 declaration exchange
commit_move(payload: dict) -> {"ok": bool}            # hash only; response = Acknowledge
reveal_move(payload: dict) -> {"ok": bool}             # move+hint, nonce withheld
submit_audit(payload: dict) -> {"passed": bool, "verified_steps": int, "failed_steps": list[int]}
get_revealed_records(payload: dict) -> {"records": list[dict]}   # added post-Stage-8, see below
receive_barrier_declaration(payload: dict) -> {"ok": bool}   # {"row": int, "col": int}, added post-Stage-8
receive_capture_claim(payload: dict) -> {"confirmed": bool}   # {"reason": "barrier"|"stuck"}, added post-Stage-8
```
**`receive_barrier_declaration`/`receive_capture_claim`, added after Stage 8
shipped (rules 21/22/46 fix):** `domain/rules.py::is_captured_by_barrier`
existed and was unit-tested since Stage 1 but had zero call sites in the
live match loop — no wire channel existed for the Cop to ever tell this
peer a barrier was placed. The book prescribes no wire shape for this
(confirmed against the Cop repo's own `WIRE-CONTRACT.md`, which
independently reached the same conclusion) — this repo's own choice, not
yet reconciled with the Cop side's `receive_barrier_declaration(col, row)`/
`receive_capture_claim(...)` (different parameter shapes, and theirs
includes both agents' coordinates where this one deliberately doesn't).
`receive_capture_claim` never trusts an unverified claim: it only confirms
what this peer has already independently determined locally (a barrier
landed on its own current cell, or it has no legal moves) — rule 22 (never
falsely declare a capture) is the *claimant's* obligation; this is this
peer's own defense against a false claim from the other side.

**`get_revealed_records`, added after Stage 8 shipped (rules 19/36 fix):**
`finalize_match` originally only ever called `submit_audit` on the
opponent (submitting this peer's own records to be audited by them) --
genuinely one-directional, never auditing the opponent's own log. This
tool is the other half: actively pull the opponent's full revealed log
(only answerable once *that* peer has itself decided the match is over,
per rule 18) and run `audit_records()` on it locally. See `PRD_8` §2.1's
addendum and `peer/match_end.py`'s own docstring for the full story.

(`negotiate`/`receive_control`'s actual return shapes were also corrected
here in Stage 8 to match what `peer/handshake.py`'s already-built
`run_handshake` genuinely requires — the original `{"ok": bool}` sketch for
every tool was never accurate for these two.)

**`AuditPayload`:**
```json
{"sender": "thief", "result_claim": "survival",
 "records": [{"payload": {"state": "...", "move": "...", "intent": "...", "nonce": "..."},
              "commit": "..."}]}
```

**Step-0 declaration (sealed, sent before move 1):**
```json
{"step": 0, "type": "system_spec",
 "spec": {"os": "...", "cpu": "...", "ram_gb": 32, "gpu": "...", "vram_gb": 12},
 "model": "...", "code_version": "1.00", "github_commit_hash": "<sha1 of HEAD>",
 "group_name": "..."}
```

**Shared `game.json` required terms (fail-fast if any missing):** `grid_size`,
`thief_start`, `cop_start`, `move_set` (must be exactly `["N","S","E","W","STAY"]`),
`max_moves`, `survival_threshold`, scoring block, `pheromone_center_intensity`
(0.9), `pheromone_decay` (0.10), `pheromone_grid_size` (5), `hint_max_words`. All
values loaded from the Mandatory Parameters Table (Appendix ו), respecting each
parameter's constant/minimum/negotiable status — never hardcoded/invented.
These are *our* local field names (`config/thief/game.json`'s own schema) — the
Cop repo is free to name its equivalents differently; see ADR-6 for how
`negotiate()` reconciles the two without requiring identical key names.

**`negotiate()` payload (see ADR-6) — canonical named dict, not our raw `game.json`:**
```json
{"terms": {"grid_size": 7, "num_agents": 2, "axis_origin_corner": "top-left",
           "axis_start_index": 0, "thief_start": [3, 3], "cop_start": [0, 0],
           "map_area": "New York", "hint_word_limit": 15,
           "move_set": ["N", "S", "E", "W", "STAY"], "max_barriers": 14,
           "max_moves": 35, "survival_threshold": 35,
           "capture_reward_cop": 20, "capture_reward_thief": 5,
           "survival_reward_cop": 5, "survival_reward_thief": 10,
           "tie_score": 2, "technical_loss": 0,
           "scent_center_intensity": 0.9, "scent_decay_rate": 0.10,
           "scent_field_size": 5},
 "nonce": "...", "commit": "sha256 hex"}
```
Key set and names are fixed by `negotiation.CANONICAL_TERM_KEYS` —
`negotiation.canonical_terms(config)` builds this dict from our own
`ConfigManager`; the receiver does the same from theirs and `verify_peer`
compares key-by-key, naming the exact field on any mismatch.

**4 JSON report artifacts (schema-level, per match):**
1. **declaration** — `game_id`, `game_uid`, timestamps, `num_sub_games`,
   `groups.{group_1,group_2}{identity, repos, mcp_servers, spec, llm_model}`
2. **config** — the shared terms verbatim + `config_sha256` + `config_name`
3. **log** — per-sub-game `records[]` (`{payload, nonce, commit}`),
   `audit{passed, verified_steps, failed_steps}`, mutual-agreement signature
4. **result** — aggregate outcome across sub-games, `final_result{winner_group,
   tokens_total_series}`, mutual-agreement signature

**Gmail report:** the `result` artifact (at minimum) sent as a **structured JSON
attachment** — plain-text body is explicitly forbidden — to the fixed recipient
in `config/thief/game.toml [email]`, routed through `ApiGatekeeper`.

---

## 6. Consistency Check Against PRD.md

- Milestones in `PRD.md` §6 (7-stage table) match the module layout above 1:1 —
  no stage introduces a module not accounted for here.
- Non-goals in `PRD.md` §2.3 (no LLM-driven moves, no shared code with Cop, RL
  not required) are all enforced architecturally here (ADR-1, ADR-7, separate
  repo with zero shared modules).
- Acceptance criteria in `PRD.md` §2.2 map to: public-URL reachability (§1
  layout + Stage 5), Commit-Reveal/audit (ADR-3/ADR-6), belief map driving
  decisions (ADR-1 + `strategy/fleeing_brain.py`), GUI/Replay `Verified OK`
  (ADR-8 + `gui/replay_view.py`), Gmail JSON reporting (ADR-4 + `report/`).

**Next steps after this PLAN.md is approved:** `docs/TODO.md` (task breakdown)
→ then the 7 per-stage PRD files, one at a time, each implemented and tested
before the next begins.
