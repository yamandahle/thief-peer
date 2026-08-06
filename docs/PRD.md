# Product Requirements Document — Thief Peer

**Project:** Police-Thief P2P — Distributed Cops-and-Robbers over a Peer-to-Peer Network
**Course:** Orchestration of AI Agents — Final Project
**This repo's role:** THIEF peer (the Cop peer is a separate, independently-built repo
owned by teammate, per the book's mandatory "full environment separation" rule)
**Governing documents:** `police_thief_p2p.pdf` v3.0.0 (game spec), `software_submission_guidelines-V3.pdf` v3.00 (engineering standards)
**Status:** DRAFT — pending approval before PLAN.md / TODO.md / code

---

## 1. Overview and Context

### 1.1 What this project is
A fully decentralized (peer-to-peer, no central server, no referee) pursuit game
between two autonomous AI agents — a Cop and a Thief — on a discrete grid. There
is no central process holding "ground truth": each agent is its own independent
program, running its own FastMCP server and client, communicating only over the
network with the opponent's exposed tools. Trust between the two mutually-
distrusting sides is established purely through cryptography (Commit-Reveal /
SHA-256), never through a shared referee or shared code/state.

This repository implements **only the Thief side**. It must be able to play a
full, legal match against *any* correctly-implemented Cop peer — including one
built by a different team in the class league — using nothing but the shared,
signed `config/game.json` contract and the MCP protocol.

### 1.2 The problem being solved
The Thief has **partial observability**: it never sees the Cop's true position.
It knows only (a) its own true position with certainty, (b) the Cop's decaying
scent trail (an unfakeable physical signal), and (c) the Cop's free-form natural-
language hints (which may lie). The Thief must build a probabilistic belief about
where the Cop is, and choose moves that maximize survival — while itself emitting
a scent trail and optionally sending deceptive hints of its own.

### 1.3 Target audience / graders
The course lecturer, grading against: (a) this repo's own correctness/quality in
isolation, and (b) this peer's ability to actually complete legal, verifiable
matches against independently-built rival peers in the live league.

---

## 2. Goals and Success Metrics

### 2.1 The four graded success metrics (book Ch.11, Table 4)
| Metric | What it means for the Thief peer |
|---|---|
| **Coordination** | Correct P2P turn management over FastMCP, no central judge, clean handling of rival disconnects/timeouts |
| **Adaptation** | A genuine belief map (Bayesian update from scent + hints) that measurably drives movement decisions |
| **Integrity** | Commit-Reveal/SHA-256 sealing on every step; a mutual post-match audit that would actually catch tampering |
| **Architecture** | SDK-layered design, Gatekeeper/Orchestrator discipline, resilience to failure (per guidelines PDF) |

### 2.2 Acceptance criteria (binding, from book's Final Pre-Submission Checklist, Ch.11)
- [ ] Base game engine runs end-to-end cleanly, scoring correct
- [ ] Connects to the Cop peer over a **public URL** (tunnel), not just localhost
- [ ] Commit-Reveal + mutual audit passes with no tampering detected
- [ ] Scent map + belief map computed AND demonstrably influence movement decisions
- [ ] Live GUI + Replay App both show **"Verified OK"**
- [ ] Automated, structured JSON report sent to `[agent report address]` via Gmail API after every legal match
- [ ] GitHub repo with Git Tag + academic README.md, cross-linked to the Cop repo
- [ ] Played ≥ `[minimum games to pass]` = **2** (status: constant) league matches against **different** opponent groups
- [ ] Self-scored on code quality only, per guidelines PDF checklist (not league win/loss)

### 2.3 Non-goals / explicitly out of scope
- The move decision is **never** delegated to an LLM (hard rule, Ch.6) — the one
  narrow "mutual agreement" exception is **not** being pursued for this project.
- No shared code, shared memory, or shared process with the Cop peer, even
  though both repos are developed by the same two-person team.
- Reinforcement learning is **not required** — one optional track among three
  equally-valid ones (heuristic / custom algorithm / RL). Default plan: custom
  algorithm on top of the belief map (see PRD_3_strategy.md, later).

---

## 3. Functional Requirements

1. **P2P networking (FastMCP)** — run as both MCP server (exposing tools the Cop
   calls) and MCP client (calling the Cop's exposed tools). No central server.
2. **Board & movement** — grid `[board size]` (status: minimum, example 7×7),
   movement = `[N,S,E,W,STAY]` only (status: **constant**, no diagonals). Thief
   cannot place barriers (Cop-only mechanic).
3. **Scent emission & absorption** — emit own scent field on every move/stay
   (`[scent intensity at center]`=0.9, `[scent decay rate]`=0.10, `[scent field
   size]`=5×5 — all status: **constant**); absorb and decay the Cop's received
   scent field identically.
4. **Belief map** — Bayesian-style probability grid over the Cop's likely
   location, updated from received scent + hints, diffused each turn.
5. **Strategy (own work, not LLM)** — pure-Python decision policy: choose the
   legal move that **maximizes** distance from the believed Cop location
   (Manhattan distance), with room to improve beyond the naive greedy baseline
   (this is the graded "Adaptation" differentiator).
6. **Deceptive hints** — natural-language hint each turn, self-declared
   truth/lie verdict, capped at `[hint max words]` (status: negotiable, example
   15). LLM used **only** for this text layer if enabled (see §3.7) — never for
   the move.
7. **Commit-Reveal security protocol** — every step: `Hcommit =
   SHA256(State‖Move‖Intent‖Nonce)` sent first; Move+hint revealed next; all
   Nonces revealed at match end for mutual audit. `secrets` module for Nonce,
   canonical/sorted JSON, constant-time hash comparison.
8. **Step-0 declaration** — signed pre-game hardware spec + exact GitHub commit
   hash of code being played, sent before move 1 of every match.
9. **Capture / survival rules** — a barrier placed on the Thief's current cell,
   or the Thief having no legal move, both count as instant capture. Thief wins
   by surviving to `[survival threshold]` (status: minimum, example 35) moves.
10. **GUI** — local Tkinter live view showing only this peer's local truth (own
    position, own trail, belief heatmap of the Cop) — never the Cop's real
    position. Turn banner reflecting the async turn state machine.
11. **Replay Simulator** — steps through a saved match log, re-verifying every
    Commit-Reveal hash live, flags `Verified OK` / `TAMPERED`.
12. **Automated Gmail reporting** — after every legal match, independently send
    a structured JSON report (one of the 4 mandatory artifacts) to
    `[agent report address]` via Gmail API/OAuth2. Gatekeeper pattern (quota +
    rate-limit token bucket + DOS detector) protecting the send path.
13. **League participation** — declare games-played-so-far honestly each match;
    play ≥2, ≤10 (status: constant) counted games against distinct rivals.

### 3.4 User stories
- *As the Thief agent*, I want to build a probabilistic belief about the Cop's
  location from decaying scent and possibly-lying hints, so that I can choose
  moves that keep me away from where the Cop most likely is.
- *As the Thief agent*, I want to occasionally send a deceptive hint about my
  location, so that I can mislead the Cop's belief map without ever being able
  to fake my own scent trail (which is physically unfakeable by design).
- *As the Thief agent*, I want every move I commit to be cryptographically
  sealed, so that neither I nor the Cop can dispute what actually happened
  after the match ends.
- *As a grader*, I want to open this repo alone and find a complete, documented,
  reproducible implementation with no dependency on the Cop repo's source code.

---

## 4. Non-Functional Requirements (from software_submission_guidelines-V3.pdf)

- **Architecture**: all business logic behind one SDK entry point; GUI/CLI call
  the SDK only.
- **File size**: ≤150 code lines per file.
- **Testing**: TDD (Red→Green→Refactor), ≥85% coverage, `pytest`.
- **Linting**: zero `ruff check` violations.
- **No hardcoded values**: all game parameters from `config/game.json` /
  `game.toml`; no magic numbers/URLs/timeouts inline.
- **Secrets**: env vars only, `.env-example` committed with dummy values,
  `.gitignore` covers all secret files (`credentials.json`, `token.json`, etc).
- **Package management**: `uv` only, never `pip`/`venv` directly.
- **API Gatekeeper**: all external calls (Gmail, LLM if enabled) centralized
  through one rate-limited, queued, retrying gatekeeper.
- **Docs-first**: this PRD.md → PLAN.md → TODO.md → per-mechanism PRDs, all
  approved before implementation begins.

---

## 5. Assumptions, Limitations, Dependencies

- **Assumes** the Cop peer (built independently by teammate, or by rival teams
  in the league) correctly implements the identical shared `config/game.json`
  contract — verified via mutual SHA-256 signature exchange before each match.
- **Assumes** Python 3.13+, `uv`, `FastMCP` available in the runtime environment.
- **Depends on** a tunneling tool (ngrok/Localtonet) for public reachability
  during real league play; localhost-only is acceptable for local dev/testing.
- **Depends on** Gmail API + OAuth 2.0 setup (Appendix א) for the mandatory
  reporting step — not yet configured as of this draft.
- **Limitation**: this repo cannot be tested standalone for a full match — it
  requires a running, config-compatible Cop peer (either teammate's repo, the
  lecturer's sample repo in stub mode, or a league rival).
- **Out of scope for this repo**: any Cop-side logic, shared state, or shared
  code with the Cop repo.

---

## 6. Timeline and Milestones (mapped to book Ch.10's 7-stage build order)

Each stage below gets its own `docs/PRD_<n>_<name>.md` (created after this
PRD.md, PLAN.md, and TODO.md are approved) and a binary go/no-go milestone
before moving to the next stage — no skipping ahead.

| # | Stage | Milestone (binary pass/fail) |
|---|---|---|
| 1 | Base logic (grid, movement, no barriers for thief) | Thief agent moves legally on the grid in isolation |
| 2 | Basic FastMCP infra (localhost) | Raw message from a peer received and decoded correctly on localhost |
| 3 | First "blind" strategy module | Thief computes a legal move toward a target with no manual intervention |
| 4 | Language + scent integration | Scent map updates turn-by-turn; hint emitted every step (true or lie) |
| 5 | Public URL + tunnel | Connects to a remote Cop peer over a real tunnel, session updates mutually |
| 6 | Commit-Reveal + Step-0 | Move committed and revealed with Nonce; Step-0 hardware evidence ready |
| 7 | Reporting shell (Gmail, GUI, Replay) | Match summary sent via Gmail; GUI shows status; Replay shows recorded session |

**Next steps after this PRD is approved:** `docs/PLAN.md` (architecture: C4
diagrams, module layout, ADRs) → `docs/TODO.md` (task breakdown) → then the 7
per-stage PRDs above, one at a time, each implemented and tested before the
next begins.
