"""Wraps std_v1's own revealed turn records into the same generic
`{"payload": {..., "nonce": ...}, "commit": ...}` shape `gui/replay_view.py`
already steps through for native/cop_v1 logs -- but verified with std_v1's
own commit scheme (`interop/std_v1/crypto.py::commit_of`), which is *not*
interchangeable with `domain/crypto.py::CommitReveal` (see that module's
own docstring: the nonce is hashed differently in each scheme). Records are
paired with the commit this side actually sent live for that step (captured
by round_loop.py/police_round_loop.py as `my_commits`), never a commit
recomputed after the fact -- the same "verify against what was actually
seen live" principle `audit.py::verify_peer_records` already applies to the
peer's own records.
"""

from __future__ import annotations

from thief_peer.interop.std_v1.sealing import verify_record

_VERIFIED_OK = "Verified OK"
_TAMPERED = "TAMPERED"


def build_records(records: list[dict], commits: dict[int, str], sub_game_number: int) -> list[dict]:
    """`records` are `sealing.py::build_audit_record`'s own flat
    `{**payload, "nonce": nonce}` shape; `commits` is the matching
    step -> commit map this side recorded at seal time. Entries whose step
    has no matching commit (shouldn't happen for this side's own records,
    but guarded rather than assumed) are skipped rather than written with
    a fabricated commit."""
    wrapped = []
    for record in records:
        commit = commits.get(record.get("step"))
        if commit is None:
            continue
        wrapped.append({"sub_game_number": sub_game_number, "payload": record, "commit": commit})
    return wrapped


def verify_step(entry: dict) -> str:
    """Same contract as `gui/replay_view.py::verify_step`, but checked
    against std_v1's own commit scheme via `sealing.py::verify_record`
    (already the correct, spec-matching implementation used live during
    play)."""
    payload = entry["payload"]
    if verify_record(payload, entry["commit"]):
        return _VERIFIED_OK
    return _TAMPERED


def audit_records(records: list[dict]) -> dict:
    """Same summary shape as `domain/crypto.py::audit_records`, for the
    `"audit"` field `report/artifacts.py::build_log` expects -- verified
    against std_v1's own scheme, not native's."""
    failed_steps: list[int] = []
    for index, entry in enumerate(records):
        if verify_step(entry) == _TAMPERED:
            failed_steps.append(index)
    return {
        "passed": len(failed_steps) == 0,
        "verified_steps": len(records),
        "failed_steps": failed_steps,
    }
