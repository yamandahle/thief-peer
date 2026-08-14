# Final Pre-Submission Checklist (book Ch.11, p.96-97)

**What this file is:** the book's own end-of-project checklist — a
summary of everything chapters 1-11 already covered, reframed as a final
go/no-go gate before submitting. **Not being worked through yet** — this
is parked here until the section-by-section book walkthrough
(`BOOK_WALKTHROUGH.md`) is finished, per your instruction. Each item below
is cross-linked to the relevant bug-list item or confirmed-compliant note
already on record, so the final pass is mostly "go check these specific
things," not starting from zero.

**Status legend:** ⏳ pending review · will become ✅ / ❌ once actually
re-verified during the final pass.

## 1. Base Logic & Engine

- ⏳ A full series of sub-games runs end-to-end without crashing.
- ⏳ All physical rules (scoring, barriers, movement) strictly match
  `PARAMETERS.md`. *(Likely fine — confirmed repeatedly through the
  walkthrough, e.g. Part 4. Re-check bug item 5, opponent move/barrier
  legality, before calling this fully closed.)*

## 2. Public P2P Connectivity

- ⏳ Agents can actually talk over the public internet (ngrok/Localtonet),
  not just localhost. *(Proven once already, earlier this project, with a
  real live tunnel test — re-confirm it still works before submission,
  tunnels/tokens can go stale.)*

## 3. Cryptographic Integrity (Audit)

- ⏳ A real test game, replayed, shows "Verified OK" for every step.
- ⏳ Any hash mismatch actually triggers a Technical Loss. *(This is
  exactly bug items 1 and 2 on the master list — the reveal-before-ack
  gap and the score-not-zeroed-on-failed-audit gap. Both need to be fixed
  before this box can honestly be checked.)*

## 4. Observation Maps (Ch.4 & 6)

- ⏳ Scent Map and Belief Heatmap both actually exist and genuinely
  influence movement, not just decoration. *(Already confirmed — this is
  core to `ThiefBrain`'s scoring. Low risk, quick re-check.)*

## 5. Mandatory User Interfaces

- ⏳ Live GUI shows the real-time belief heatmap.
- ⏳ Replay App loads a log and verifies Commit-Reveal signatures.
  *(Both exist and work — see bug items 6/7 for the two known
  refinements: GUI missing scent/hint panels, replay not halting on
  tamper. Neither blocks this box, both are worth fixing first anyway.)*

## 6. Automated Reporting

- ⏳ Gmail API correctly configured to auto-send `result_...json` and
  `log_...json` to the lecturer's address. *(Deliberately not written
  into any file yet, per your instruction — this needs the real address
  filled in during the final pass, not before.)*
- ⏳ Both Cop and Thief send independently. *(This side already does —
  confirm the Cop side does too when you're in touch with your teammate.)*

## 7. GitHub Submission & Tags

- ⏳ Two separate repos (Cop, Thief).
- ⏳ README.md has the Dec-POMDP model, strategy description, and the
  mandatory screenshots. *(Screenshots are the one open item — same 2 as
  the rest of the walkthrough. Dec-POMDP/strategy sections already
  written, see `README_PLAN.md` for the polish items still queued.)*
- ⏳ Git tag (e.g. `v1.0-submission`) marking the exact graded version.
  *(Not done — correctly so, this is a last step, not something to do
  mid-development.)*

## 8. League Requirements

- ⏳ Played against at least 2 different teams.
- ⏳ Never exceeded 10 games against any one opponent. *(Bug items 10/12
  on the master list — nothing currently enforces either of these in
  code; this is as much a "did we actually do it" question as a "does the
  code check it" question.)*

---

**When we come back to this:** work top to bottom, actually re-verifying
each box (not just trusting the walkthrough's earlier notes) — a couple
of these depend on bugs from the master list being fixed first (item 3
depends on bug items 1+2), and a couple are genuinely last-step-only
(the git tag, the real lecturer email) and shouldn't be done early.
