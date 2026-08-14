# Every number the game uses — checked against this repo

**What this file is:** the book has one appendix (Appendix F) that's the
single official source for every number in the game — board size, points,
timeouts, everything. Nowhere else in the book counts; if the book's main
text and this table ever seem to disagree, this table wins. Extracted
directly from the book on 2026-08-14, and checked line-by-line against
`config/thief/game.json`.

**Bottom line: every single number in your config already matches the
book exactly.** ✅ next to everything below.

## Three kinds of values

- **Fixed** — cannot be changed at all. Both sides must use the exact
  book value.
- **Minimum** — a floor. Both teams can agree to raise it, never lower it.
  If nothing's agreed, use the book's example value.
- **Negotiated** — either side may propose a different number, but if
  nothing's agreed, default to the book's example value.

## Board & starting positions

| Setting | What it means | Book's value | Type | Your config |
|---|---|---|---|---|
| Board size | side length of the square grid | 7×7 | Minimum | 7×7 ✅ |
| Number of agents | players in the game | 2 | Fixed | 2 ✅ |
| Corner that's (0,0) | which corner the grid counts from | top-left | Negotiated | top-left ✅ |
| Axis start number | what number each axis starts at | 0 | Negotiated | 0 ✅ |
| Thief's start cell | where the thief begins | (3,3), the centre | Negotiated | (3,3) ✅ |
| Cop's start cell | where the cop begins | (0,0), a corner | Negotiated | (0,0) ✅ |

## World & hints

| Setting | What it means | Book's value | Type | Your config |
|---|---|---|---|---|
| Map area | real-world city name used in hints | "New York" | Negotiated | "New York" ✅ |
| Max words per hint | length limit on every hint sent | 15 words | Negotiated | 15 ✅ |

## Movement & barriers

| Setting | What it means | Book's value | Type | Your config |
|---|---|---|---|---|
| Allowed moves | up/down/left/right + stay, no diagonals | N/S/E/W/STAY | Fixed | matches ✅ |
| Max barriers | how many barriers the cop can place | 14 | Minimum | 14 ✅ |
| Max moves | length limit on one sub-game | 35 | Minimum | 35 ✅ |
| Survival threshold | steps the thief must survive to win | 35 | Minimum | 35 ✅ |

## Scent trail (pheromones)

| Setting | What it means | Book's value | Type | Your config |
|---|---|---|---|---|
| Scent strength at source | how strong the trail is right where you stood | 0.9 | Fixed | 0.9 ✅ |
| Scent decay rate | how fast the trail fades each turn | 0.10 | Fixed | 0.10 ✅ |
| Scent emission size | size of the "splash" each step leaves behind | 5×5 | Fixed | 5×5 ✅ |

## Scoring system

Straight from the book (Table 2 p.22 / Table 17 p.138) — matches exactly
what you sent:

| Event | Cop score | Thief score |
|---|---|---|
| Successful capture | 20 | 5 |
| Thief survives 35 moves | 5 | 10 |
| Technical loss (cheating/timeout/tampered log) | 0 | 0 |
| Tie — **series total** across all 6 games vs. one opponent ties | 2 | 2 |

Your config: 20 / 5 / 5 / 10 / 0 / 2 — all ✅, matches exactly.

**On cheating, in plain terms:** every move first gets sent as a locked
"commit" (a hash) before either side reveals the real move + a secret
number (the nonce). After the game, the Replay Viewer recomputes those
hashes from the revealed data. If even one doesn't match — that's
`TAMPERED`, and per the book, that's final: automatic 0-0, no appeal, no
fixing it after the fact. See `RULES.md`'s "🔴 Fix this one" note — your
code detects this correctly but doesn't currently zero the score.

## League & series

| Setting | What it means | Book's value | Type | Your config |
|---|---|---|---|---|
| Games per series | sub-games played against one opponent | 6 | Fixed | 6 ✅ |
| New-opponent bonus | bonus for beating a team you haven't played | 10 | Fixed | 10 ✅ |
| Minimum games to pass | least games a team must play to get a passing grade | 2 | Fixed | 2 ✅ |
| Max games per team | most games any team is allowed to play total | 10 | Fixed | 10 ✅ |
| Token budget per series | LLM tokens allowed for a whole series | ~200,000 | Negotiated | 200,000 ✅ |

## Network protection (rate limiting)

| Setting | What it means | Book's value | Type | Your config |
|---|---|---|---|---|
| Requests per minute | max outgoing API calls per minute | 30 | Minimum | 30 ✅ |
| Concurrent requests | max requests in flight at once | 2 | Minimum | 2 ✅ |
| Retry wait time | pause before retrying after an error | 5 sec | Minimum | 5 ✅ |
| Max retries | attempts before giving up | 3 | Minimum | 3 ✅ |
| Queue depth | how many requests can wait in line | 100 | Minimum | 100 ✅ |
| Response timeout | how long to wait for any one network reply | 30 sec | Negotiated | 30 ✅ |
| Watchdog freeze threshold | how long before the watchdog steps in | 60 sec | Negotiated | 60 ✅ |

## The 4 report files (reference only — not negotiated)

| File | What it's for |
|---|---|
| `declaration_<game_id>.json` | pre-game declaration: teams, members, repos, hardware, model, tokens, timing |
| `config_<game_id>_g<NN>.json` | the agreed, locked settings for one sub-game |
| `log_<game_id>_g<NN>.json` | the sub-game's full move log, for cryptographic verification |
| `result_<game_id>.json` | the final result, used for league scoring |

## Which LLM mode you use (your own private choice, not negotiated)

| Mode | Cost | Actually wired into a real match today? |
|---|---|---|
| `template` | free, 0 tokens | ✅ yes — this is what every real match uses right now |
| `ollama` | free, 0 API tokens | ⚠️ the code exists and works, but nothing in `game.toml` can switch to it yet — `runtime_setup.py` always builds with no LLM provider |
| `claude_api` | real cost, counted against token budget | ❌ stub only — raises "not implemented yet" if called |
| `claude_cli` | highest cost | ❌ stub only — same as above |

Since this repo runs in `template` mode, a whole series can be played at
zero token cost — the competition then comes down entirely to how good the
movement algorithm is, which is this repo's actual differentiator. Fully
compliant either way — `template` is the book's own recommended default.
Switching to `ollama` would need a small wiring change (a config-driven
provider selection), not new provider code.
