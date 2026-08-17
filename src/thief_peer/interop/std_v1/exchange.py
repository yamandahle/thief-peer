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
        return self._wait_for_either_key(self._audits, sub_game_number, timeout, "audit envelope")

    def wait_for_consensus(self, timeout: float) -> dict:
        """The final series_consensus envelope carries no sub_game_number
        at all -- always the None-keyed bucket."""
        return self._wait_for(self._audits, None, timeout, "consensus envelope")

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
