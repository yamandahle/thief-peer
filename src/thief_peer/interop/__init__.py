"""Cop-repo interop adapter: translates between this repo's own native wire
vocabulary and the Cop repo's actual, independently-built MCP surface
(`https://github.com/Nagham1023/yamanagh-cop`) -- verified directly against
her cloned source, not guessed from the book alone (two independently-built
peers ended up with completely different tool names/payload shapes, since
the book never mandates one).

Scope: Step-0 declaration exchange, scent-map push/pull translation,
per-turn commit/reveal/barrier/capture tool-name/payload routing, and (as of
the follow-up to `docs/PRD_9_cop_interop.md`, after a real live run against
her actual process surfaced two concrete bugs) an auto-firing
`receive_capture_response` and a genuinely-sent `receive_final_reveal`.

`peer/sealing.py::sealed_step_record` now hashes the same 7-field envelope
shape her `integrity/commit_reveal.py::CommitEnvelope` does (`state, move,
intent, nonce, hint_text, step, role`) -- adopted as this team's own
intra-pair standard (this team controls both repos; no other league
opponent speaks this repo's `"native"` protocol at all, confirmed by
`grep`, so the change doesn't constrain any other opponent). For the
`cop_v1` path specifically (`interop/cop_round_loop.py::play_round_cop`),
`state`/`move`/`intent` are no longer this side's own internal shapes --
`interop/cop_wire.py::build_cop_state_string`/`build_cop_move_envelope`
reconstruct exactly what her own `integrity/peer_trace.py::run_peer_audit`
independently derives by replaying this peer's revealed moves (`own_pos`
as `[col, row]`, `steps_taken`, `barriers_placed` always `[]` since the
thief role never places one) and her own wire-received move shape
(`{"type": "move", "direction": ...}`), and `intent` is a real `bool`
(her own `run_peer_audit` does `bool(entry.intent)` on whatever arrives,
and a non-empty string is truthy either way -- silently wrong, not a
crash, if this side ever sent a string instead). Empirically verified
byte-for-byte against her actual cloned `commit()` +
`canonical_state_bytes` for a fixed scenario (`tests/unit/test_cop_wire.py`).
This makes her side's own audit of *this* peer's per-turn commits
genuinely possible, not just wire-compatible.

Still NOT closed, and not closable from this side alone: the reverse
direction. There is no documented tool on her server for this peer to pull
her own revealed records and audit HER -- `WIRE-CONTRACT.md`'s tool table
has no `get_revealed_records`-equivalent. `peer/match_end.py`'s
`opponent_audited_by_me` therefore stays honestly "not evaluated" for
`cop_v1`, not a false pass. A genuine, cross-team follow-up (would need a
new tool on her side), not an oversight on this one.
"""
