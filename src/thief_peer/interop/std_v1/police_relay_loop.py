"""Per-sub-game turn loop for std_v1's Police role, sourcing the actual
move decision from a separate `yamanagh-cop` process over a local-only
network call (never a Python import -- see that repo's own
`std_v1/relay_server.py` docstring) instead of this repo's own minimal
`police_brain.py` stand-in. Everything else -- the wire protocol,
sealing, and audit-record shape -- is byte-for-byte what
`police_round_loop.py`'s own loop already does and what's already proven
working against yanell11; only the source of the move decision changes,
and that source now seals its own commit/nonce before handing it back, so
the real move secret never exists inside this process either.

`relay_transport` is this repo's own `infra/mcp_client.py::McpTransport`,
constructed once per series and pointed at the relay's loopback port --
reused verbatim rather than writing a second transport class, since the
four-tool wire client (`wire.py::send_turn` etc.) already proves that
"call a tool, get a dict back" abstraction works for this shape too.
"""

from __future__ import annotations

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.interop.std_v1.sealing import build_audit_record, build_step0_record, build_turn_message
from thief_peer.interop.std_v1.wire import send_turn


def play_sub_game_as_police(
    transport,
    exchange,
    max_steps: int,
    turn_deadline_sec: float,
    relay_transport,
    sub_game_number: int,
    on_phase=None,
    github_commit: str | None = None,
) -> tuple[str, list[dict], dict[int, str], dict[int, str]]:
    """Mirrors `police_round_loop.py::play_sub_game_as_police`'s return
    shape and wire behavior exactly -- see that module's own docstring for
    the full protocol reasoning. Position/belief/scent state now lives
    entirely inside the relay's own `Std1TurnHandler`, so this loop
    doesn't need `board`/`state`/`scent`/`thief_start` at all.

    `github_commit` here is yamanagh-cop's own commit (fetched once via
    `relay_identity`, threaded down from std_v1_opponent.py), not this
    process's -- it's genuinely yamanagh-cop's own code playing this role,
    so its step-0 declaration should say so (see round_loop.py::
    play_sub_game's own docstring for why this record exists at all)."""

    def _phase(name: str) -> None:
        if on_phase is not None:
            on_phase(name)

    records: list[dict] = [build_step0_record("police", github_commit)]
    peer_commits: dict[int, str] = {}
    my_commits: dict[int, str] = {}

    relay_transport.call("start_police_subgame", {"sub_game_number": sub_game_number})

    try:
        thief_message = exchange.wait_for_turn(1, timeout=turn_deadline_sec)
    except DeadlineExceededError:
        return "timeout", records, peer_commits, my_commits
    peer_commits[1] = thief_message["commit"]
    print("[turn 1] received thief opening", flush=True)
    last_thief_scent = thief_message.get("smell_grid") or {}
    last_thief_hint = thief_message.get("hint") or ""

    thief_step = 1  # last Thief step actually received
    while thief_step <= max_steps:
        police_step = thief_step  # this round's reply carries the same number
        _phase("COMPUTING_MOVE")
        decision = relay_transport.call(
            "decide_police_turn",
            {"step": police_step, "thief_smell_grid": last_thief_scent, "thief_hint_text": last_thief_hint},
        )
        payload = decision["payload"]
        records.append(build_audit_record(payload, decision["nonce"], decision["commit"]))
        my_commits[police_step] = decision["commit"]
        _phase("COMMITTING")
        send_turn(transport, build_turn_message(payload, decision["commit"]))
        print(f"[turn {police_step}] sent move={payload['move']} (relayed)", flush=True)

        _phase("AWAITING_REVEAL")
        try:
            thief_message = exchange.wait_for_turn(thief_step + 1, timeout=turn_deadline_sec)
        except DeadlineExceededError:
            return "timeout", records, peer_commits, my_commits
        print(f"[turn {thief_message['step']}] received thief reply", flush=True)
        peer_commits[thief_message["step"]] = thief_message["commit"]

        _phase("VERIFYING")
        claim_response = thief_message.get("claim_response") or {}
        if claim_response.get("caught") is True:
            return "capture", records, peer_commits, my_commits
        if (thief_message.get("win_claim") or {}).get("type") == "survival":
            return "survival", records, peer_commits, my_commits

        last_thief_scent = thief_message.get("smell_grid") or {}
        last_thief_hint = thief_message.get("hint") or ""
        _phase("WAITING_FOR_OPPONENT")
        thief_step += 1

    return "survival", records, peer_commits, my_commits
