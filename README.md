# Police-Thief P2P — Thief Peer

**Course:** Orchestration of AI Agents (Dr. Yoram Segal, University of Haifa)
**This repo's role:** THIEF peer — a fully independent, decentralized (P2P)
pursuit-game agent with no shared code or state with the Cop peer, per the
project's mandatory "full environment separation" rule.

> **Status: planning complete, implementation not yet started.** This repo
> currently contains the full docs-first planning stack (`PRD.md` →
> `PLAN.md` → `TODO.md` → 7 per-stage PRDs/TODOs). Code is built stage by
> stage from here, each with its own binary milestone before advancing.

## What this is

Two autonomous AI agents — a Cop and a Thief — chase each other on a
discrete grid with **no central server and no referee**. Each side is a
fully independent process, communicating only via FastMCP over the network,
using scent-trail-based partial observability (stigmergy) and a
Commit-Reveal/SHA-256 protocol so neither side can cheat without being
cryptographically caught. Full formal background: Dec-POMDP formalism,
scoring, security model — see `docs/PRD.md`.

## Docs

Start with `docs/PRD.md` (requirements) → `docs/PLAN.md` (architecture,
module layout, ADRs, API contracts) → `docs/TODO.md` (build order index).
Each of the 7 build stages has its own `docs/PRD_<n>_<name>.md` (design) and
`docs/TODO_<n>_<name>.md` (task checklist), covering:

1. Base logic (grid, movement, capture/survival rules)
2. FastMCP infrastructure (localhost)
3. Strategy module (the evasion algorithm — the graded differentiator)
4. Language + scent integration (belief map, LLM-generated hints)
5. Public URL + tunnel reachability
6. Commit-Reveal crypto sealing + Step-0 hardware declaration
7. Reporting shell (Gmail+OAuth, live GUI, replay simulator)

## Cop repo

Link to the paired Cop peer repo: _to be added once available_.

## Running it

Not yet runnable — Stage 1 implementation is next. Once scaffolded, this
section will document `uv sync` / `uv run` usage per `docs/PLAN.md`.
