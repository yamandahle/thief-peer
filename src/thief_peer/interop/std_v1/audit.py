"""Per-sub-game mutual audit and final series-consensus exchange (spec
Sections 9-11). Same mutual, idempotent-resend shape as
handshake.py::negotiate_sub_game -- Section 9's own "both MUST be sent
promptly" and Section 10's explicit consensus-exchange steps.
"""

from __future__ import annotations

import time

from thief_peer.exceptions import DeadlineExceededError, SimulationError, TransportError
from thief_peer.interop.std_v1.sealing import verify_record
from thief_peer.interop.std_v1.wire import send_audit

WIRE_ROLES = ("police", "thief")


def build_audit_envelope(
    sender: str, records: list[dict], result_claim: str, sub_game_number: int
) -> dict:
    return {
        "sender": sender,
        "records": records,
        "result_claim": result_claim,
        "sub_game_number": sub_game_number,
    }


def build_consensus_envelope(sender: str, consensus_sha: str) -> dict:
    """Section 10 step 3: no `sub_game_number` at all -- this is what lets
    StdExchange's None-keyed bucket route it correctly."""
    return {
        "sender": sender,
        "result_claim": "series_consensus",
        "records": [],
        "consensus_sha": consensus_sha,
    }


def send_and_await(
    transport,
    wait_fn,
    envelope: dict,
    resend_interval_sec: float = 2.0,
    ceiling_sec: float = 60.0,
) -> dict:
    """Shared resend-until-matched loop for both the per-sub-game audit
    and the final consensus exchange -- `wait_fn(timeout)` is
    `exchange.wait_for_audit(sub_game_number, ...)` or
    `exchange.wait_for_consensus(...)`, injected so this one loop serves
    both without duplicating it."""
    deadline = time.monotonic() + ceiling_sec
    while time.monotonic() < deadline:
        try:
            send_audit(transport, envelope)
        except TransportError:
            # Same reasoning as handshake.py::negotiate_sub_game -- submit_audit
            # is idempotent per spec Section 7, so a transient failure (peer's
            # tunnel briefly down) is always safe to retry, not fatal.
            remaining = deadline - time.monotonic()
            time.sleep(min(resend_interval_sec, max(0.0, remaining)))
            continue
        remaining = deadline - time.monotonic()
        try:
            return wait_fn(timeout=min(resend_interval_sec, max(0.0, remaining)))
        except DeadlineExceededError:
            continue
    raise DeadlineExceededError(f"no matching audit response within {ceiling_sec}s")


def turn_records_only(records: list[dict]) -> list[dict]:
    """Some peers' own kits disclose an extra per-sub-game metadata record
    alongside their real turn records -- e.g. yanell11's own kit, live: a
    "Step-0 host-spec record" with `payload.type == "system_spec"`. It was
    never sent live through receive_turn, so this side never saw a commit
    for it; verify_peer_records' own "unseen step -> tampered" rule (a
    deliberate anti-cheat guard against a peer fabricating a turn it never
    actually played, see test_verify_peer_records_rejects_a_record_for_a_
    step_we_never_saw_a_commit_for) would misfire on it every time.
    Filtered out narrowly by its own declared type, not by "unseen step"
    in general, so a genuinely fabricated turn record is still caught."""
    return [r for r in records if (r.get("payload") or {}).get("type") != "system_spec"]


def peer_github_commit(records: list[dict]) -> str | None:
    """A peer's own system_spec disclosure record (see `turn_records_only`'s
    own docstring) can declare its own `github_commit` inline -- read here
    since it's the peer's own declaration inside its sealed audit envelope,
    not something to take on faith from a side channel. This value was
    never sent live through receive_turn (same reasoning as
    `turn_records_only`), so it isn't part of this side's own commit-reveal
    verification -- informational for the filed report only, same trust
    level the negotiate-offer identity.github_commit field already had.
    `None` if no such record is present or it doesn't declare one."""
    for record in records:
        payload = record.get("payload") or {}
        if payload.get("type") == "system_spec" and payload.get("github_commit"):
            return payload["github_commit"]
    return None


def verify_peer_records(records: list[dict], peer_commits: dict[int, str]) -> dict:
    """Section 9's own mutual audit: re-hash every one of the peer's
    revealed records and compare against the commit this side actually
    saw live for that step (`peer_commits`, from round_loop.py's own
    play_sub_game) -- never against a commit the record merely claims for
    itself, which would let a peer approve its own tampering."""
    mismatched_steps = []
    for record in records:
        step = (record.get("payload") or {}).get("step")
        expected_commit = peer_commits.get(step)
        if expected_commit is None or not verify_record(record, expected_commit):
            mismatched_steps.append(step)
    return {
        "log_verified": not mismatched_steps,
        "tampered": bool(mismatched_steps),
        "mismatched_steps": mismatched_steps,
    }


def build_sub_game_row(
    sub_game_number: int,
    result: str,
    roles: dict[str, str],
    score: dict[str, int],
    winner_group: str | None,
) -> dict:
    """Section 11's own exactly-five-key row shape."""
    return {
        "sub_game_number": sub_game_number,
        "result": result,
        "roles": dict(roles),
        "score": dict(score),
        "winner_group": winner_group,
    }


def build_consensus_object(game_id: str, game_uid: str, sub_games: list[dict]) -> dict:
    """Section 11's own exactly-three-key top-level object, rows ordered
    strictly by ascending sub_game_number -- callers may append rows out
    of order across a series, so this always re-sorts rather than trusting
    call order."""
    ordered = sorted(sub_games, key=lambda row: row["sub_game_number"])
    return {"game_id": game_id, "game_uid": game_uid, "sub_games": ordered}


def validate_consensus_envelope(envelope: dict) -> str:
    """Section 10 step 3's own explicit acceptance rules. Returns the
    peer's own consensus_sha on success; raises SimulationError otherwise
    -- a malformed envelope here must never be silently treated as
    agreement."""
    if envelope.get("result_claim") != "series_consensus":
        raise SimulationError("consensus envelope has the wrong result_claim")
    if envelope.get("records") != []:
        raise SimulationError("consensus envelope must carry an empty records list")
    consensus_sha = envelope.get("consensus_sha")
    if not isinstance(consensus_sha, str) or len(consensus_sha) != 64 or any(
        c not in "0123456789abcdef" for c in consensus_sha
    ):
        raise SimulationError("consensus envelope's consensus_sha is not 64 lowercase hex chars")
    if envelope.get("sender") not in WIRE_ROLES:
        raise SimulationError(
            f"consensus envelope's sender must be a wire role {WIRE_ROLES}, "
            f"got {envelope.get('sender')!r}"
        )
    return consensus_sha


def confirm_agreement(
    all_sub_games_audited_clean: bool,
    all_sub_game_results_agreed: bool,
    local_digest: str,
    peer_digest: str,
) -> bool:
    """Section 10 step 4: agreement is confirmed only when every remote
    log verified untampered, every sub-game result was mutually agreed,
    AND the received remote digest equals the local one -- a locally
    computed digest alone never confirms anything by itself."""
    return all_sub_games_audited_clean and all_sub_game_results_agreed and local_digest == peer_digest
