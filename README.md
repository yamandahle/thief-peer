# Police-Thief P2P — Thief Peer

**Course:** Orchestration of AI Agents (Dr. Yoram Segal, University of Haifa)
**This repo's role:** THIEF peer — a fully independent, decentralized (P2P)
pursuit-game agent with no shared code or state with the Cop peer, per the
project's mandatory "full environment separation" rule.

## Status

All 7 planned stages (`docs/PRD_1`…`docs/PRD_7`) have their components built
and individually tested: 260 tests, 96%+ line coverage (`gui/*` excluded from
the coverage gate per `pyproject.toml`), ruff-clean. An end-to-end smoke test
(`tests/integration/test_end_to_end_smoke.py`) wires a scripted match through
board/brain/belief → Commit-Reveal sealing → the four report artifacts →
the rate-limited Gatekeeper → a stubbed Gmail send, and proves they compose
correctly.

**Known gap — no live-match entry point yet.** `docs/PLAN.md`'s own
architecture names `peer/runtime.py` (`PeerRuntime`) as the orchestrator that
should wire negotiation → the turn loop → sealing/audit → reporting into one
continuously-running match, driven by `cli.py run` / the GUI. That class was
never actually built — every stage's `TODO_<n>.md` deferred it forward as
"arriving once `PeerRuntime` exists," and no stage ever claimed it as its own
task, so it fell through. The MCP server currently only exposes `ping` and
`submit_audit`; the real `negotiate` / `receive_turn` tools it would need for
a genuine match against the Cop peer are not wired either. The CLI's only
subcommand today is `smoke-test` (a single `ping` round-trip). Building
`PeerRuntime` and the missing MCP tools is necessary follow-up work before
this peer can play an actual game — it is not part of Stage 7's scope as
originally task-listed, and is flagged here rather than silently left for a
grader to discover.

## What this is

Two autonomous AI agents — a Cop and a Thief — chase each other on a
discrete grid with **no central server and no referee**. Each side is a
fully independent process, communicating only via FastMCP over the network,
using scent-trail-based partial observability (stigmergy) and a
Commit-Reveal/SHA-256 protocol so neither side can cheat without being
cryptographically caught. Full formal background, scoring, and the security
model: see `docs/PRD.md`.

## Docs

Start with `docs/PRD.md` (requirements) → `docs/PLAN.md` (architecture,
module layout, ADRs, API contracts) → `docs/TODO.md` (build order index).
Each of the 7 build stages has its own `docs/PRD_<n>_<name>.md` (design) and
`docs/TODO_<n>_<name>.md` (task checklist):

1. Base logic (grid, movement, capture/survival rules)
2. FastMCP infrastructure (localhost)
3. Strategy module (the evasion algorithm — the graded differentiator)
4. Language + scent integration (belief map, LLM-generated hints)
5. Public URL + tunnel reachability
6. Commit-Reveal crypto sealing + Step-0 hardware declaration
7. Reporting shell (Gmail+OAuth, live GUI, replay simulator)

## Running it

```
uv sync                                   # install dependencies
uv run pytest --cov=thief_peer            # full test suite + coverage gate (85%)
uv run ruff check .                       # lint
uv run python -m thief_peer smoke-test --config <path-to-your-game.toml>
```

The `smoke-test` subcommand starts this peer's FastMCP server and pings a
configured `network.opponent_url` — it does **not** play a match (see the
gap noted above). It requires a private `game.toml` you create yourself,
minimally providing `network.my_port` and `network.opponent_url`
(`ConfigManager`, `docs/PLAN.md` ADR-5). No sample `config/` directory ships
in this repo yet, since nothing consumes a full config until `PeerRuntime`
exists.

## Config split

Two files, merged by one `ConfigManager` (`shared/config.py`, ADR-5):

- **`game.json`** — shared, signed terms both peers must agree on byte-for-
  byte (grid size, move limits, etc.) — negotiated and hash-verified via the
  same `CommitReveal` primitive used for per-turn sealing (DRY, ADR-6).
- **`game.toml`** — private, local-only terms (network port, opponent URL,
  strategy/LLM class selectors, email recipient).

On a key collision the JSON value always wins — it's the signed, mutually-
agreed term; the private TOML must never be able to quietly weaken it.

## Strategy / LLM extension points

`strategy/brain_base.py`'s `resolve_brain(config)` loads a `BrainBase`
subclass via a dotted-path selector (`[strategy] thief_class =
"pkg.module:ClassName"` in `game.toml`), defaulting to the shipped
`ThiefBrain` (`strategy/fleeing_brain.py`). `BrainBase.decide()` structurally
never lets a strategy's *move* computation touch an LLM — only
`strategy/trash_talk.py`'s hint/verdict banter (Stage 4) calls an LLM
provider, and only through `talk_providers.py`'s pluggable adapters
(template / ollama / claude_api / claude_cli), themselves only reachable
through `shared/gatekeeper.py`'s rate-limited `ApiGatekeeper` (ADR-4).

## Academic sections (Ch.9 §9.4.2)

**Dec-POMDP model.** Each peer is a partially-observable Markov decision
process participant: the true joint state (both agents' positions) is never
fully known to either side (`gui/window.py`'s `PeerView` dataclass
structurally has no opponent-position field — ADR-8, enforced at the type
level, not by GUI-drawing convention). Observations arrive only as scent
intensity readings the opponent's movement leaves behind
(`domain/scent.py`'s 5×5 diffusion-and-decay kernel, book Fig. 4 exactly:
center 0.90, orthogonal 0.62, diagonal 0.42, range-two orthogonal 0.20,
range-two diagonal 0.14, corners 0.04, applied via
`τij(t+1) = max(0, (1−ρ)·τij(t) + Δτij)`). `domain/belief.py`'s `BeliefGrid`
turns that into a probability distribution over the opponent's position
(Bayesian update + per-turn diffusion for the fact that they moved since the
last observation), and the strategy in `strategy/fleeing_brain.py` acts on
the *full distribution* (expected distance, weighted by belief probability),
never a `most_likely()`-only shortcut.

**FastMCP orchestration challenges.** Running two independently-built,
mutually-distrusting peers over FastMCP surfaced two concrete problems this
repo had to design around: (1) tool payloads must be wrapped as a single
`{"payload": {...}}` argument, not passed as loose keyword arguments — every
MCP tool in `infra/mcp_server.py` follows this shape uniformly; (2) real
network failures are slower than they look in a unit test — a genuinely
unreachable `Client` connection attempt took several seconds of internal
retry before failing, which meant test deadlines tuned against a mocked
transport were too tight against the real one (`infra/mcp_client.py`'s
`DeadlineExceededError` vs. `TransportError` distinction exists specifically
because of this).

**Gatekeeper / Orchestrator design.** `shared/gatekeeper.py`'s
`ApiGatekeeper` is the single doorway every outbound Gmail or LLM call must
pass through (ADR-4) — never called directly from `infra/email_sender.py` or
`infra/llm_provider.py`. It chains a `DosDetector` (a circuit breaker that
hard-locks on anomalous call volume, protecting the account *before* the
provider notices, not after), a `TokenBucket` (lazy-refilled
`tokens ← min(C, tokens + r·Δt)`), and a bounded `RequestQueue` (overflow
requests queue rather than silently drop), with real retry/backoff on 429s
and every attempt logged regardless of outcome.

**Strategy used.** `ThiefBrain` is a hand-tuned weighted-sum policy, not
reinforcement learning: full-distribution expected distance from the belief
map (weight 1.0), 1-ply mobility at the candidate cell (weight 1.5 — the
signal that actually keeps it out of dead-end pockets, tuned empirically
against a constructed corner-trap board), a 1-ply minimax lookahead against
the Cop's best response from its most-likely position (weight 0.1), and a
least-recently-visited tie-break to avoid predictable back-and-forth
trails. See `strategy/fleeing_brain.py` for the exact scoring.

**Screenshots (mandatory).** _Not included — capturing these requires a live
desktop session and is a manual step; see below._

**Cop repo.** _Link to be added once available._

## Manual steps this repo cannot perform for you

- **Gmail OAuth setup and a real sent-email verification.** `infra/email_sender.py`
  is fully tested against a fake Gmail service double, but actually sending a
  report requires your own Google Cloud OAuth credentials, one-time browser
  consent, and a `token.json` — none of which can be created or verified from
  here.
- **The two mandatory submission screenshots** (Live GUI belief heatmap,
  Replay "Verified OK" stamp) — the Tkinter GUI's rendered appearance can
  only be confirmed by actually running it on a visible desktop.
- **Building and exercising `PeerRuntime`** against a real, independently
  running Cop peer — the gap described above.
