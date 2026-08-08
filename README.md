# Police-Thief P2P — Thief Peer

**Course:** Orchestration of AI Agents (Dr. Yoram Segal, University of Haifa)
**This repo's role:** THIEF peer — a fully independent, decentralized (P2P)
pursuit-game agent with no shared code or state with the Cop peer, per the
project's mandatory "full environment separation" rule.

## Status

All 8 stages (`docs/PRD_1`…`docs/PRD_8`) are built and tested: 332 tests,
96%+ line coverage (`gui/*` excluded from the coverage gate per
`pyproject.toml`), ruff-clean. `peer/runtime.py`'s `PeerRuntime` is the real
live-match orchestrator — `cli.py run --group-name ... --config ...` drives
handshake → every round's commit/reveal → the end-of-match mutual audit →
a Gmail report, automatically. `tests/integration/test_live_match.py` proves
this with two real `PeerRuntime` instances, each with its own live FastMCP
server, playing a full match to completion over real localhost sockets.

**Known limitation.** This repo has no Cop-peer implementation (the Cop is a
separate, independently-built repo per the book's "zero shared code" rule),
so the live-match proof above is necessarily two Thief `PeerRuntime`
instances pointed at each other — real proof the protocol/orchestration
machinery works end to end, not a claim of having tested against actual Cop
gameplay logic. Playing a real match against the teammate's Cop repo is
listed below as a manual step.

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
8. `PeerRuntime` + the live-match MCP tools (`docs/PRD_8_peer_runtime.md` —
   a gap found after Stage 7 shipped, not part of the original 7-stage plan)

## Running it

```
uv sync                                   # install dependencies
uv run pytest --cov=thief_peer            # full test suite + coverage gate (85%)
uv run ruff check .                       # lint
uv run python -m thief_peer smoke-test --config config/thief/game.toml
uv run python -m thief_peer run --group-name "Your-Team-Name" \
    --config config/thief/game.toml --shared-config config/thief/game.json
```

`run` drives a full live match against `network.opponent_url` to completion.
`smoke-test` is a lighter diagnostic (a single `ping` round-trip). Real
starter files ship at `config/thief/game.toml` (private) and
`config/thief/game.json` (shared, Appendix ו's default values) — before a
real run, edit `game.toml`'s two placeholder fields:
`network.opponent_url` (the Cop peer's actual reachable MCP URL) and
`email.recipient` (currently `CHANGE-ME@example.com`). `game.json`'s values
are this repo's own starting proposal, not yet negotiated/hashed with the
Cop peer — see the "Cop repo interop" note below before assuming they're
final.

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

**Cop repo.** `https://github.com/Nagham1023/yamanagh-cop`

## Cop repo interop status

As of the last check (Stage 8), the Cop repo was through its own PRD 5
(cloud exposure) with PRD 6 (Commit-Reveal) and PRD 7 (reporting/GUI) not
yet started — no real match is possible yet regardless of wire compatibility,
since a match without Commit-Reveal on both sides isn't rules-compliant.
Their own draft wire contract (`WIRE-CONTRACT.md`, at the time explicitly
marked "not yet sent to the teammate") proposed a materially different tool
surface for hint/scent than this repo's `commit_move`/`reveal_move`: two
separate tools (`receive_hint`, `share_scent_map`) instead of one bundled
message, a pull rather than push model for scent, and a `[col, row, value]`
triple list rather than this repo's `{"row,col": value}` dict. The shared
`game.json` schema and values, by contrast, already matched closely — that
part is unlikely to need rework. Plan: wait for the Cop repo to reach PRD 6/7,
then jointly reconcile the wire contract before attempting a real connection.

## Manual steps this repo cannot perform for you

- **Gmail OAuth setup and a real sent-email verification.** `infra/email_sender.py`
  is fully tested against a fake Gmail service double, but actually sending a
  report requires your own Google Cloud OAuth credentials, one-time browser
  consent, and a `token.json` — none of which can be created or verified from
  here.
- **The two mandatory submission screenshots** (Live GUI belief heatmap,
  Replay "Verified OK" stamp) — the Tkinter GUI's rendered appearance can
  only be confirmed by actually running it on a visible desktop.
- **Playing a real match against the teammate's independently-built Cop
  repo** — `PeerRuntime` is built and proven against a second real instance
  of itself (see "Known limitation" above), but a genuine cross-repo match
  needs their process actually running, on their machine or a shared
  tunnel, which isn't something this repo can simulate or fake.
