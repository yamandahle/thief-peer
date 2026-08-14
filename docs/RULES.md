# The book's 55 rules — checked against this repo

**What this file is:** the book has an appendix (Appendix E) listing 55
things you're required to do or forbidden from doing. This file lists all
55, in plain language, with a check for whether this repo's code already
does it. Built 2026-08-14 by reading the book directly and checking every
rule against the actual source code (not guessed).

**How to read it:** skip straight to "The short version" below — that's
all you need day to day. The full 55-item table is further down, for
reference, if you ever want to check one specific rule.

---

## The short version

### 🔴 Fix this one — it's a real bug

**When the game detects cheating (a tampered log, or the two sides'
reports disagreeing), the score should drop to 0-0 — but right now it
doesn't.**

The book is very strict about this (its own words: *"There is no appeal
and no after-the-fact correction"* for a tampered log). Your code already
correctly **notices** when something's wrong and writes `tampered: true`
into the report — but it forgets to also zero out the actual score
numbers next to it. So the JSON honestly admits cheating happened, while
still reporting normal points. That's the one thing worth fixing before
anything else.

*(Rules 19 and 35 below — this is the same bug showing up under both.)*

### 🟡 Small things worth doing, no rush

Nothing urgent, but easy to knock out while we're going through the book
anyway:

- No button for auto-launching a tunnel (ngrok) — you do it by hand right
  now, which works fine, just not as convenient as it could be. *(Rule 10)*
- If two teams agreed to weaken a "minimum" setting (e.g. fewer barriers
  than the book allows), nothing would catch it. *(Rule 12)*
- Nothing stops you from accidentally counting the same opponent twice
  toward your score, or forgets to check you've played enough different
  opponents. *(Rules 31, 52)*
- The `--group-name` you type in isn't checked to be exactly 8 characters,
  no spaces, like the book asks. *(Rule 45)*
- Not fully confirmed yet whether "games played so far" gets honestly told
  to the opponent at the start of a match. *(Rules 37, 38 — needs another look)*

### 🟢 Already good

Everything else — 45 of the 55 rules — is already handled correctly:
separate processes, no shared memory, a real state machine, timeouts on
every wait, a watchdog, the live GUI only ever shows your own info (never
the enemy's true position), the whole commit-reveal/nonce/audit security
system, orthogonal-only movement, honest barrier declarations, natural-
language-only communication (no coordinate-sharing), Gmail rate limiting
and send-only permission, JSON-only reports, secrets kept out of git, and
so on. Full list in the table below if you want the details.

### ⚪ Not code — things a human has to do at submission time

- Downloading/filling the Moodle form (Rule 43)
- Each teammate submitting individually on Moodle (Rule 44)
- Writing the short "self-grade my own code quality" note (Rule 55)
- Tagging the final Git commit and taking the 2 required screenshots —
  these aren't done *yet*, but that's expected at this stage of the
  project, not a bug (Rules 41, 42 — see `BOOK_WALKTHROUGH.md`'s
  screenshot checklist)

---

## Full 55-rule reference table

Legend: ✅ done · ❌ gap · ❓ needs a closer look · ⚪ human step, not code

### Group 1 — Network setup & keeping each side honest (book p.142-144)

| # | Rule | Status | Where in the code |
|---|---|---|---|
| 1 | Thief and Cop run as two totally separate processes | ✅ | `interop/cop_opponent.py` — only talks to the Cop over the network |
| 2 | Never share memory/variables between the two sides | ✅ | No Cop code is ever imported into this repo |
| 3 | One single orchestrator controls everything | ✅ | `PeerRuntime` in `peer/runtime.py` |
| 4 | Game progress is managed by a proper state machine | ✅ | `peer/turn_fsm.py` |
| 5 | An illegal state change must be rejected, not ignored | ✅ | `TurnFsm.transition()` raises an error |
| 6 | Every wait on the opponent has a timeout | ✅ | `infra/mcp_client.py` |
| 7 | A watchdog catches a frozen/crashed process | ✅ | `shared/watchdog.py` |
| 8 | The live GUI shows only your own true information | ✅ | `gui/window.py` |
| 9 | The live GUI must never show the real opponent position | ✅ | `gui/board_view.py` |
| 10 | Use a tunnel tool to expose your server to the internet | ❌ | Works, but only if you run ngrok by hand — no built-in shortcut |

### Group 2 — Board & movement rules (p.144)

| # | Rule | Status | Where in the code |
|---|---|---|---|
| 11 | Both sides' config files must be byte-for-byte identical | ✅ | `domain/negotiation.py` checks a hash of the file |
| 12 | A "minimum" setting may only go up, never down | ❌ | Nothing currently checks this |
| 13 | Move only up/down/left/right | ✅ | `domain/board.py` |
| 14 | No diagonal moves allowed | ✅ | Diagonals don't exist as an option in the code |
| 15 | Every barrier placement must be openly declared | ✅ | `interop/cop_peer_audit.py` |
| 16 | Never lie about where a barrier was placed | ✅ | Caught automatically by the same audit |

### Group 3 — Cryptographic security (p.145-146)

| # | Rule | Status | Where in the code |
|---|---|---|---|
| 17 | Use SHA-256 Commit-Reveal for every move | ✅ | `domain/crypto.py` |
| 18 | Keep the secret "nonce" hidden until the game ends | ✅ | `domain/protocol.py` |
| 19 | A tampered log must force the cheating side's score to 0 | ❌ | **See "Fix this one" above** |
| 20 | Build a Replay Viewer to verify the game log afterward | ✅ | `cli.py replay` |
| 21 | Only ever tell the truth when claiming a capture | ✅ | Capture is computed by the game engine, not a free claim |
| 22 | Never falsely claim a capture that didn't happen | ✅ | Same as above, plus the mutual audit would catch a lie |
| 23 | Lock the scent-map formula cryptographically before the game | ✅ | `domain/scent_lock.py` |
| 24 | Cryptographically declare your hardware before the game | ✅ | `shared/sysinfo.py` |

### Group 4 — Talking & the language model (p.146)

| # | Rule | Status | Where in the code |
|---|---|---|---|
| 25 | (Recommended, not required) Don't let the LLM pick the move | ✅ | `strategy/fleeing_brain.py` — pure Python decides movement |
| 26 | Communicate only in free natural language | ✅ | `strategy/talk_providers.py` |
| 27 | Never send your exact coordinates as data | ✅ | No message ever contains a position field |
| 28 | Rate-limit outgoing Gmail sends | ✅ | `shared/rate_limiter.py` |
| 29 | Detect and block runaway/DOS-style request patterns | ✅ | `shared/rate_limiter.py`'s `DosDetector` |
| 30 | Gmail access must be "send only," nothing more | ✅ | `infra/email_sender.py` |

### Group 5 — Fair play & submission logistics (p.147-148)

| # | Rule | Status | Where in the code |
|---|---|---|---|
| 31 | Play the required minimum number of counted games | ❌ | Nothing enforces this yet |
| 32 | Auto-send match results by Gmail | ✅ | Happens automatically at match end |
| 33 | Reports must be structured JSON | ✅ | `report/artifacts.py` |
| 34 | Never send the report as plain text — JSON attachment only | ✅ | `infra/email_sender.py` |
| 35 | If reports disagree/are missing, both sides score 0 | ❌ | **See "Fix this one" above** |
| 36 | Run a full mutual log audit at the end of every game | ✅ | `peer/match_end.py` |
| 37 | Honestly declare how many games you've played so far | ❓ | Tracked internally, not confirmed sent to the opponent |
| 38 | Never lie about how many games you've played | ❓ | Same as above |
| 39 | Never push secrets/credentials into the repo | ✅ | Confirmed not tracked by git |
| 40 | Add credential files to `.gitignore` | ✅ | Already there |
| 41 | Tag the final submitted version in Git | ⚪ | Not done yet — expected at this stage, do it before final submission |
| 42 | Write an academic report with screenshots | ❌ | Screenshots still missing — tracked in `BOOK_WALKTHROUGH.md` |
| 43 | Fill out the Moodle submission form | ⚪ | Human step |
| 44 | Every team member submits individually | ⚪ | Human step |
| 45 | Team code must be exactly 8 characters, no spaces | ❌ | Not currently checked/enforced |

### Group 6 — Extra rules found elsewhere in the book (p.149-150)

| # | Rule | Status | Where in the code |
|---|---|---|---|
| 46 | A barrier dropped exactly on the thief's cell = capture | ✅ | `domain/rules.py` |
| 47 | A thief with zero legal moves also counts as captured | ✅ | `domain/rules.py` |
| 48 | Score every outcome using the official point table | ✅ | `peer/match_end.py` |
| 49 | Two separate GitHub repos, cross-linked everywhere required | ✅ | Already set up |
| 50 | Each repo needs README, configs, PRD, PLAN, TODO files | ✅ | All present |
| 51 | Auto-send reports to the lecturer's exact address | ✅ | Configured |
| 52 | Only one counted game per opponent — no repeats | ❌ | Nothing blocks a repeat |
| 53 | Record your current commit hash at the start of every game | ✅ | `interop/cop_wire.py` |
| 54 | Report total tokens used, per game and for the series | ✅ | `peer/match_end.py` |
| 55 | Self-grade your code quality only — not the match result | ⚪ | Human write-up step |
