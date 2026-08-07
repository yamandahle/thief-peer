# TODO — Thief Peer Build Order (Index)

**Status:** all 7 stage PRDs drafted and consistent with `PRD.md`/`PLAN.md`
(see each `PRD_<n>_<name>.md`) — pending review before implementation begins.

Mirrors the 7-stage order from `PRD.md` §6 / book Ch.10. Each stage must be
fully working end-to-end and tested before the next stage starts — no
skipping ahead. `uv run pytest --cov` and `uv run ruff check` must be clean
at the end of every stage. Detailed task checklists live in one file per
stage, matching the corresponding `PRD_<n>_<name>.md` 1:1:

| Stage | Task file | Book ref | Status |
|---|---|---|---|
| 1 — Base logic | [`TODO_1_base_logic.md`](TODO_1_base_logic.md) | Ch.3 | ✅ done |
| 2 — FastMCP infra (localhost) | [`TODO_2_mcp_infra.md`](TODO_2_mcp_infra.md) | Ch.2 | not started |
| 3 — Blind strategy module | [`TODO_3_strategy.md`](TODO_3_strategy.md) | Ch.6 | not started |
| 4 — Language + scent | [`TODO_4_language_scent.md`](TODO_4_language_scent.md) | Ch.4/6 | not started |
| 5 — Public URL + tunnel | [`TODO_5_cloud_tunnel.md`](TODO_5_cloud_tunnel.md) | Ch.2 | not started |
| 6 — Commit-Reveal + Step-0 | [`TODO_6_security.md`](TODO_6_security.md) | Ch.5 | not started |
| 7 — Reporting shell | [`TODO_7_reporting_shell.md`](TODO_7_reporting_shell.md) | Ch.9/7/App.א | not started |

Update each file's own `Status:` line as work progresses (e.g. `not started`
→ `in progress` → `done`); update the table above to match whenever a
stage's status changes, so this index stays a reliable at-a-glance summary.

---

## After Stage 7 — submission readiness (not a build stage, a final pass)
- [ ] Re-run the full pre-submission checklist from `PRD.md` §2.2 / book Ch.11
- [ ] Play ≥ 2 league matches against distinct opponent groups (teammate's Cop
      repo counts as one; need ≥1 more from the wider class league)
- [ ] Git tag the submission commit (`v1.0-submission`), confirm README
      cross-links to the Cop repo, confirm no secrets in git history
