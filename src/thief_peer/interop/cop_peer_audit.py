"""Audit a Cop peer from recorded commit/reveal/final-reveal data
(Ch.5.3.2 + rules 19/36): replay their moves from the shared `cop_start`,
recompute each `Hcommit`, compare with `secrets.compare_digest`.

Mirrors `yamanagh-cop`'s `integrity/peer_trace.py::run_peer_audit` for
`role="cop"` without importing that repo — same envelope fields, same
state shape (`own_pos` as `[col,row]`, sorted `barriers_placed`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from thief_peer.domain.crypto import CommitReveal

_DELTAS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}


@dataclass
class CopPeerEntry:
    h_commit: str | None = None
    move: dict | None = None
    hint_text: str | None = None
    nonce: str | None = None
    intent: bool | None = None


@dataclass
class CaptureClaim:
    claimed_at_step: int
    thief_row: int
    thief_col: int
    cop_row: int
    cop_col: int
    confirmed: bool


@dataclass
class CopPeerTrace:
    entries: dict[int, CopPeerEntry] = field(default_factory=dict)
    capture_claims: list[CaptureClaim] = field(default_factory=list)
    capture_responses: list[dict] = field(default_factory=list)
    _next_commit: int = 1
    _next_reveal: int = 1

    def record_commit(self, h_commit: str) -> None:
        step = self._next_commit
        self.entries.setdefault(step, CopPeerEntry()).h_commit = h_commit
        self._next_commit += 1

    def record_reveal(self, move: dict, hint_text: str) -> None:
        step = self._next_reveal
        entry = self.entries.setdefault(step, CopPeerEntry())
        entry.move = move
        entry.hint_text = hint_text
        self._next_reveal += 1

    def record_final_reveal(self, nonces: dict, intents: dict) -> None:
        for step_str, nonce in nonces.items():
            self.entries.setdefault(int(step_str), CopPeerEntry()).nonce = nonce
        for step_str, intent in intents.items():
            self.entries.setdefault(int(step_str), CopPeerEntry()).intent = bool(intent)

    def record_capture_claim(
        self,
        *,
        claimed_at_step: int,
        thief_row: int,
        thief_col: int,
        cop_row: int,
        cop_col: int,
        confirmed: bool,
    ) -> None:
        self.capture_claims.append(
            CaptureClaim(claimed_at_step, thief_row, thief_col, cop_row, cop_col, confirmed)
        )

    def record_capture_response(
        self, *, confirmed: bool, true_thief_row: int, true_thief_col: int
    ) -> None:
        self.capture_responses.append(
            {
                "confirmed": confirmed,
                "true_thief_row": true_thief_row,
                "true_thief_col": true_thief_col,
            }
        )


def _state_string(col: int, row: int, steps_taken: int, barriers: list[list[int]]) -> str:
    payload = {
        "own_pos": [col, row],
        "steps_taken": steps_taken,
        "barriers_placed": sorted(barriers, key=lambda pair: (pair[0], pair[1])),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _apply(col: int, row: int, move: dict, barriers: list[list[int]], size: int) -> tuple[int, int]:
    if move.get("type") == "place_barrier":
        barriers.append([int(move["col"]), int(move["row"])])
        return col, row
    direction = move.get("direction", "STAY")
    dcol, drow = _DELTAS.get(direction, (0, 0))
    ncol, nrow = col + dcol, row + drow
    if 0 <= ncol < size and 0 <= nrow < size:
        return ncol, nrow
    return col, row


def audit_cop_peer_trace(
    trace: CopPeerTrace, *, cop_start: list[int], grid_size: int
) -> dict:
    """Return `{passed, verified_steps, failed_steps, failed_capture_claims}`
    matching this repo's `domain/crypto.py::audit_records` report shape.

    Rules 21/22/36: a capture claim carries a cryptographic obligation to
    be truthful about the claimant's own position, catchable the same way
    a forged move is -- by replaying her committed/revealed trajectory
    from `cop_start` and checking it against what she declared. Any claim
    whose `claimed_at_step` never lines up with an audited step is treated
    as unverifiable, and therefore failed too: "trust me" is exactly what
    this audit exists to refuse.
    """
    failed: list[int] = []
    failed_capture_claims: list[int] = []
    col, row = int(cop_start[0]), int(cop_start[1])
    barriers: list[list[int]] = []
    checked = 0
    claims_by_step = {claim.claimed_at_step: claim for claim in trace.capture_claims}
    unmatched_claim_steps = set(claims_by_step)

    for step in sorted(trace.entries):
        entry = trace.entries[step]
        if entry.h_commit is None or entry.move is None or entry.nonce is None:
            failed.append(step)
            continue
        col, row = _apply(col, row, entry.move, barriers, grid_size)
        checked += 1
        payload = {
            "state": _state_string(col, row, step, barriers),
            "move": entry.move,
            "intent": bool(entry.intent),
            "hint_text": entry.hint_text or "",
            "step": step,
            "role": "cop",
        }
        if not CommitReveal.verify(payload, entry.nonce, entry.h_commit):
            failed.append(step)
        claim = claims_by_step.get(step)
        if claim is not None:
            unmatched_claim_steps.discard(step)
            if (claim.cop_col, claim.cop_row) != (col, row):
                failed_capture_claims.append(step)

    failed_capture_claims.extend(sorted(unmatched_claim_steps))

    return {
        "passed": len(failed) == 0 and len(failed_capture_claims) == 0 and checked > 0,
        "verified_steps": checked,
        "failed_steps": failed,
        "failed_capture_claims": failed_capture_claims,
        "evaluated": True,
    }
