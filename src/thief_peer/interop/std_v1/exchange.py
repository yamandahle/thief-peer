"""StdExchange: the std_v1 protocol's own cross-thread mailbox, same shape
as peer/round_exchange.py's RoundExchange (lock + bounded poll loop) but
generalized for this protocol's four message categories instead of two.
The MCP server thread (inbound negotiate/receive_turn/submit_audit/
receive_control calls) is the writer; the round-loop/handshake/audit code
on the main thread is the reader.

Negotiation offers and audit envelopes both have a spec-mandated
"a message without its own sub_game_number is accepted on arrival, for
whichever sub-game is currently being waited on" rule (Section 3/10) --
modeled here as a `None`-keyed bucket checked alongside the exact key,
rather than a separate special case in every caller.

`_turns` is keyed by `step` alone, and every sub-game's own step counter
restarts at 1 (Section 9) -- unlike `_offers`/`_audits`, which are already
naturally scoped by `sub_game_number` itself. `series_runner.play_series`
must call `reset_turns()` at the start of every sub-game to close a real
class of bug: a leftover step-1 message from the *previous* sub-game
still sitting in `_turns` would otherwise be mistaken for the new
sub-game's own step-1 turn the instant `wait_for_turn(1, ...)` is called.
"""

from __future__ import annotations

import threading
import time

from thief_peer.exceptions import DeadlineExceededError


def _audit_belongs_to(envelope: dict, sub_game_number: int) -> bool:
    """True if `envelope` can be trusted as belonging to `sub_game_number`
    -- its own declared field if present (explicit disagreement is a
    definite reject, not just inconclusive), else the sub_game_number
    embedded in its own disclosed records, checked at both the record
    wrapper's own top level (this repo's own convention, replay_log.py::
    build_records) and inside `payload` (yanell11's own kit's convention)
    since a peer's schema is free to differ. An envelope with no records
    at all (Section 10's own explicit consensus envelope always has
    `records: []`) is never routed here -- wait_for_consensus owns that
    shape entirely -- so an empty list here has nothing to check and is
    trusted rather than rejected outright."""
    declared = envelope.get("sub_game_number")
    if declared is not None:
        return declared == sub_game_number
    records = envelope.get("records") or []
    if not records:
        return True
    return any(
        record.get("sub_game_number") == sub_game_number
        or (record.get("payload") or {}).get("sub_game_number") == sub_game_number
        for record in records
    )


class StdExchange:
    def __init__(self, poll_interval: float = 0.05):
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._offers: dict[int | None, dict] = {}
        self._turns: dict[int, dict] = {}
        self._audits: dict[int | None, dict] = {}
        self._controls: list[dict] = []

    # --- negotiation offers (Section 3) ---

    def record_offer(self, message: dict) -> None:
        with self._lock:
            self._offers[message.get("sub_game_number")] = message

    def wait_for_offer(self, sub_game_number: int, timeout: float) -> dict:
        return self._wait_for_either_key(self._offers, sub_game_number, timeout, "negotiation offer")

    # --- turn messages (Section 9) ---

    def record_turn(self, message: dict) -> None:
        with self._lock:
            self._turns[message["step"]] = message

    def wait_for_turn(self, step: int, timeout: float) -> dict:
        return self._wait_for(self._turns, step, timeout, "turn")

    def reset_turns(self) -> None:
        """Clears every recorded turn -- must be called once per sub-game,
        before that sub-game's own play_sub_game starts waiting, so a
        leftover message from the *previous* sub-game's identical step
        number can never be mistaken for the new one (see this class's
        own docstring)."""
        with self._lock:
            self._turns = {}

    # --- audit / consensus envelopes (Section 10) ---

    def record_audit(self, message: dict) -> None:
        with self._lock:
            self._audits[message.get("sub_game_number")] = message

    def wait_for_audit(self, sub_game_number: int, timeout: float) -> dict:
        """Section 10's own "a message without its own sub_game_number is
        accepted on arrival, for whichever sub-game is currently being
        waited on" rule is a real hazard, not just a convenience: a peer
        whose kit omits that optional envelope field entirely (confirmed
        live: yanell11's own audit envelopes never carry it, per the
        spec's own "omitted entirely when absent" wording) has every one
        of its audit envelopes land in the same None-keyed slot,
        overwriting whichever one was there before -- purely by arrival
        timing, not by which sub-game it's actually for. A stale one
        still sitting there when this side starts waiting on the *next*
        sub-game gets accepted as if it were the real thing (confirmed
        live: our own sub-game-4 wait grabbed their sub-game-3 police
        disclosure this way, producing both a spurious TAMPERED audit and
        a contradictory result_claim). Falling back to the sub_game_number
        embedded in the disclosed records themselves -- present
        regardless of the envelope's own optional field, and, per
        yanell11's own kit, sealed inside the commit so it "can't drift"
        -- is a peer-schema-agnostic way to tell a genuine match from a
        same-slot straggler, mirroring wait_for_consensus's own
        result_claim check for the identical class of bug."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                candidate = self._audits.get(sub_game_number)
                if candidate is None:
                    candidate = self._audits.get(None)
                if candidate is not None and _audit_belongs_to(candidate, sub_game_number):
                    return candidate
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(f"No audit envelope received (key={sub_game_number!r}) within {timeout}s")

    def wait_for_consensus(self, timeout: float) -> dict:
        """The final series_consensus envelope carries no sub_game_number
        at all -- always the None-keyed bucket. Spec Section 10 step 3's
        own explicit warning: "Straggler per-sub-game audits arriving in
        this window carry no consensus_sha and MUST NOT be mistaken for a
        consensus envelope." A straggler that also omits sub_game_number
        lands in this same slot -- found live (yanell11 match): our own
        final-sub-game audit crashed validate_consensus_envelope because
        this used to return the first thing in the slot unconditionally.
        Only accepts an entry that actually looks like the real consensus
        envelope; a straggler is treated as "not yet arrived" and polled
        past, giving the real one -- which record_audit's own plain
        overwrite will place in the same slot moments later -- room to
        actually land instead of never being looked at again."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                candidate = self._audits.get(None)
                if candidate is not None and candidate.get("result_claim") == "series_consensus":
                    return candidate
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(f"No consensus envelope received within {timeout}s")

    # --- control messages (receive_control) ---

    def record_control(self, message: dict) -> None:
        with self._lock:
            self._controls.append(message)

    def latest_control(self) -> dict | None:
        with self._lock:
            return self._controls[-1] if self._controls else None

    # --- shared waiting machinery ---

    def _wait_for(self, store: dict, key, timeout: float, kind: str):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if key in store:
                    return store[key]
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(f"No {kind} received (key={key!r}) within {timeout}s")

    def _wait_for_either_key(self, store: dict, key, timeout: float, kind: str):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if key in store:
                    return store[key]
                if None in store:
                    return store[None]
            time.sleep(self._poll_interval)
        raise DeadlineExceededError(f"No {kind} received (key={key!r}) within {timeout}s")
