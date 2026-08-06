# TODO — Stage 7: Reporting Shell (Gmail+OAuth, Live GUI, Replay Simulator)

See `PRD_7_reporting_shell.md` for full rationale. Book: Ch.9/7/Appendix א.
PRD milestone: "Match summary sent via Gmail; GUI shows status; Replay shows recorded session."

- [ ] `shared/rate_limiter.py`: `TokenBucket` (`tokens ← min(C, tokens + r·Δt)`)
      + FIFO queue + `DosDetector`
- [ ] `shared/gatekeeper.py`: `ApiGatekeeper.execute()` — sole doorway for
      Gmail+LLM, with 429-aware backoff, retry, and call logging
- [ ] `infra/email_sender.py`: Gmail API/OAuth2 (Appendix א setup), structured
      JSON **attachment** only (never plain text), via Gatekeeper
- [ ] `report/artifact_schemas.py` + `artifacts.py` + `artifact_helpers.py`:
      the 4 JSON artifact builders — package only, compute nothing new
      (data already sealed in Stage 6)
- [ ] `report/report_writer.py`: assemble artifacts + trigger email after
      every legal match; persisted per-opponent games-played counter
- [ ] `gui/window.py` + `board_view.py` + `turn_banner.py`: Tkinter GUI (own
      truth + belief heatmap + turn-fsm banner) — enforce ADR-8 (no Cop
      position ever, structurally not just by convention)
- [ ] `gui/replay_view.py`: step through a saved log, re-verify each
      commit-reveal hash live (reusing Stage 6's `domain/crypto.py`), show
      "Verified OK" / "TAMPERED"
- [ ] Tests: Gatekeeper quota/DOS-detector tests; email-is-always-JSON-
      attachment test; GUI-never-renders-cop-position test (assert on
      renderer inputs, per ADR-8); replay tamper-detection test; league
      counter survives simulated restart
- [ ] `README.md`: run instructions, config split explanation, strategy/LLM
      extension points, the mandatory academic sections (Ch.9 §9.4.2):
      Dec-POMDP model description, FastMCP orchestration challenges,
      Gatekeeper/Orchestrator design, strategy used, screenshots (Live GUI +
      Replay "Verified OK"), link to the Cop repo

**Done when:** after every legal match this peer automatically emails a
structured JSON report via Gmail through the Gatekeeper without risking a ban;
the live GUI shows only this peer's local truth with a correct async turn
banner; a saved log can be replayed and independently verified as OK or
flagged TAMPERED.

**Status:** not started
