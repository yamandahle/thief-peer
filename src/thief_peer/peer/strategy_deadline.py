"""Bounds the Strategy Module's own move-computation time (book Appendix
B: `step_deadline_seconds` -- "hard cap on LLM thinking per step").
Distinct from `RoundExchange`'s network-facing wait: this guards against
*our own* local `decide()`/hint-generation hanging, which the per-round
network deadline can never catch since it only bounds waits on the peer,
not our own local computation. Left unbounded, a hang here would only
ever be caught by the much coarser Watchdog (default 180s) -- by then the
opponent's own 30s network deadline has already declared them the winner
over the network (found via a systems-engineering review of this repo
against the book's own worked example, not by inspection alone).

Runs on a daemon thread so an abandoned hang (the callable never actually
returns) can't block process exit -- matching the lightweight-threading
style already used by `RoundExchange`/`HeartbeatMonitor`, not a new
`concurrent.futures` dependency. Deliberately raises the same
`DeadlineExceededError` the network deadline already uses, so both
failure modes fall through the same graceful technical-loss handling in
`PeerRuntime.run()`'s outer wrapper.
"""

import threading

from thief_peer.exceptions import DeadlineExceededError


def run_with_deadline(fn, timeout_sec: float):
    result: dict = {}

    def _target() -> None:
        try:
            result["value"] = fn()
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_sec)

    if thread.is_alive():
        raise DeadlineExceededError(
            f"Strategy computation exceeded the {timeout_sec}s deadline"
        )
    if "error" in result:
        raise result["error"]
    return result["value"]
