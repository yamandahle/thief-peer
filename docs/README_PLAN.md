# README additions — running to-do list

**What this file is:** a holding pen for things we decide, while walking
through the book, that should end up written into the real `README.md`
(the mandatory academic report — rule 42, ch.9.4.2: model description,
dilemmas, strategy, screenshots). Instead of editing the README a little
bit after every single book section, we collect items here and write them
into the README in one clean pass later — so nothing gets forgotten, and
the README doesn't end up patched 20 times.

**How to use it:** every item below is either ☐ (not written into the
README yet) or ✅ (done). When we're ready to do a README pass, work
through the ☐ items in order.

---

## ☐ Pending items

1. **☐ Explicitly walk through the book's own 8-part Dec-POMDP definition**
   (`⟨n, S, {Ai}, P, R, {Ωi}, O, γ⟩`, ch.1.3, p.4-5). README's current
   "Dec-POMDP model" paragraph covers the belief-map/partial-observability
   idea well but doesn't name all 8 parts the way the book frames it.
   Source: `BOOK_WALKTHROUGH.md`, Part 2.

2. **☐ Add the "uncertainty as a resource" dilemma** (ch.1.4, p.6): lying
   is only legal through the verbal hint — a scent trail can't be faked,
   and staying/returning to a cell only ever makes you *easier* to find
   there, never an advantage. Good "dilemma" material for the academic
   report. Source: `BOOK_WALKTHROUGH.md`, Part 2.

3. **☐ Live GUI screenshot** — belief heatmap, taken while a real match is
   running. Still not captured (needs a live desktop session).

4. **☐ Replay Viewer screenshot** — showing the "Verified OK" stamp on a
   genuine, untampered match log. Still not captured.

5. **☐ Note the deception system's real status honestly** (ch.6.5/1.4,
   "Deception Strategy"): a good dilemma for the report either way —
   either "we built `choose_verdict()` but chose not to wire it, here's
   why" (if we leave it as-is) or "here's how our hint's truth/lie intent
   actually shapes what gets said" (if we fix backlog item #14 first).
   Write this section *after* deciding whether to fix #14, not before —
   otherwise we'd have to rewrite it. Source: `BOOK_WALKTHROUGH.md`, Part 3b.

6. **☐ (Optional, not mandatory) An architecture diagram** — the
   Orchestrator (`PeerRuntime`) branching to its 5 subsystems (MCP
   Connector, Decision Module, Log Manager, Deadline Tracker, Watchdog),
   and/or the turn state-machine circle. Not one of the 2 required
   screenshots, but the book explains this exact chapter with two
   diagrams of its own (Fig. 11, Fig. 12) — recreating something similar
   would strengthen the "model description" section. Source:
   `BOOK_WALKTHROUGH.md`, Part 8.

7. **☐ (Optional, not mandatory) A 7-stage development timeline diagram.**
   Real evidence, not just a claim: `git log --oneline` shows this repo
   was actually built stage-by-stage in the book's own exact recommended
   order (ch.10) — one commit per stage, same order, same boundaries.
   Good "development process" material for the academic report. Source:
   `BOOK_WALKTHROUGH.md`, Part 10.

8. **☐ Weight-tuning experiment writeup** (rule 42's "dilemmas" section):
   the corner-camping regression story (tune once, burned by an incomplete
   simulator, reverted) plus the redone experiment is good, honest
   "strategy justification" material either way. Real-match verification
   has now happened (`docs/REAL_MATCH_COMPARISON.md`, 37 real games
   against her live RL brain, run by direct request outside the numbered
   backlog) — the mobility signal shows a real, if not yet fully pinned
   down, effect; no weights were changed. Good report material on its
   own, plus a second concrete "simulated vs. real can disagree" example
   alongside `docs/HEURISTIC_ABLATION.md`. Source: `BOOK_WALKTHROUGH.md`
   item 18, `docs/WEIGHT_TUNING_EXPERIMENT.md`,
   `docs/HEURISTIC_ABLATION.md`, `docs/REAL_MATCH_COMPARISON.md`.

*(New items get added here as later book sections turn up more things
worth putting in the README — always cross-link back to the
`BOOK_WALKTHROUGH.md` section that found them.)*

---

## ✅ Already in the README (confirmed present, nothing to do)

- Dec-POMDP / belief-map explanation (exists, just not the full 8-tuple —
  see item 1 above)
- Strategy description (`ThiefBrain`'s weighted-sum policy, the four
  signals it combines)
- Cop-repo interop status and cross-link
- "Going live" / tunnel runbook
- Manual-steps list (Gmail OAuth, screenshots, real match against the Cop)

---

## Reference — what rule 42 / ch.9.4.2 actually requires

Straight from `RULES.md`: a comprehensive academic report, as a readable
file in the repo — model description, dilemmas faced, strategy used,
screenshots, and RL curves *if applicable*. This repo isn't RL-based, so
no RL curves are needed — confirmed N/A, not a gap.
