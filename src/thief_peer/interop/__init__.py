"""Cop-repo interop adapter: translates between this repo's own native wire
vocabulary and the Cop repo's actual, independently-built MCP surface
(`https://github.com/Nagham1023/yamanagh-cop`) -- verified directly against
her cloned source, not guessed from the book alone (two independently-built
peers ended up with completely different tool names/payload shapes, since
the book never mandates one).

Scope, deliberately: Step-0 declaration exchange, scent-map push/pull
translation, and per-turn commit/reveal/barrier/capture tool-name/payload
routing -- everything needed for a real connection to reach the turn loop.
Explicitly OUT of scope: making this side's own per-turn `h_commit` verify
against her real end-of-match audit. Her `Hcommit` is a 7-field envelope
(`state, move, intent, nonce, hint_text, step, role`,
`integrity/commit_reveal.py`); this repo's own sealing
(`peer/sealing.py::sealed_step_record`) is a 3-field one (`state, move,
intent`). A live match against her will complete negotiation, Step-0, and
every turn's commit/reveal/scent exchange, but her final mutual audit will
report a false mismatch on this side's revealed records until the two
sealing schemes are reconciled -- a known, deliberate boundary, not an
oversight (see `docs/PRD_9_cop_interop.md`).
"""
