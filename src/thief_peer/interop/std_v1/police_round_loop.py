"""Per-sub-game turn loop for std_v1's Police role (spec Sections 5, 9,
10) -- used only on the alternated sub-games (Section 6) when this repo
plays the opposite of its natural Thief role. Movement comes from
police_brain.choose_police_move (a minimal greedy pursuit, not the
book's real ThiefBrain investment); the wire protocol, capture-claim and
sealing machinery are identical to round_loop.py's own Thief-role loop,
with sender/turn-order swapped and this side declaring the
capture-claim instead of answering one. Also emits its own self-centered
scent every turn, matching Appendix D's worked example (both roles
report a `smell_grid`, not only the Thief) -- same snapshot-before-
advance ordering as round_loop.py, for the identical one-turn-delayed
reason.
"""

from __future__ import annotations

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.interop.std_v1.police_brain import believed_thief_cell, choose_police_move
from thief_peer.interop.std_v1.sealing import (
    build_audit_record,
    build_turn_message,
    build_turn_payload,
    seal_turn,
)
from thief_peer.interop.std_v1.wire import send_turn


def _move_token(direction) -> str:
    return direction.value if direction is not None else "STAY"


def play_sub_game_as_police(
    board,
    state,
    scent,
    transport,
    exchange,
    max_steps: int,
    turn_deadline_sec: float,
    thief_start,
    on_phase=None,
) -> tuple[str, list[dict], dict[int, str], dict[int, str]]:
    """Mirrors round_loop.py::play_sub_game's return shape (now also
    returning `my_commits`, this side's own live commits keyed by step,
    for the same replay-log-pairing reason). Waits for the Thief's own
    step-1 turn first (Section 10: "the Thief sends the first turn of
    each sub-game"), then alternates on even step numbers.

    `on_phase`, if given, is called with one of TurnFsm's own state names
    (peer/turn_fsm.py) at each of that book state machine's transition
    points -- see round_loop.py::play_sub_game's own docstring for the
    same convention; this loop starts already "waiting for the opponent"
    (the Thief's step-1 message), so its first phase call is the same
    COMPUTING_MOVE transition round_loop.py's loop makes on its first
    iteration."""

    def _phase(name: str) -> None:
        if on_phase is not None:
            on_phase(name)

    records: list[dict] = []
    peer_commits: dict[int, str] = {}
    my_commits: dict[int, str] = {}

    try:
        thief_message = exchange.wait_for_turn(1, timeout=turn_deadline_sec)
    except DeadlineExceededError:
        return "timeout", records, peer_commits, my_commits
    peer_commits[1] = thief_message["commit"]
    last_thief_scent = thief_message.get("smell_grid") or {}

    step = 1
    while step <= max_steps:
        step += 1
        _phase("COMPUTING_MOVE")
        target = believed_thief_cell(last_thief_scent, tuple(thief_start))
        direction = choose_police_move(board, state.position, frozenset(state.known_barriers), target)
        state.apply_move(direction, board)
        payload = build_turn_payload(
            step=step,
            sender="police",
            move=_move_token(direction),
            hint="",
            smell_grid=scent.snapshot(),
            barrier_placed=None,
            capture_claim=list(state.position),
        )
        sealed = seal_turn(payload)
        records.append(build_audit_record(payload, sealed["nonce"]))
        my_commits[step] = sealed["commit"]
        _phase("COMMITTING")
        send_turn(transport, build_turn_message(payload, sealed["commit"]))
        scent.advance(state.position)

        _phase("AWAITING_REVEAL")
        try:
            thief_message = exchange.wait_for_turn(step + 1, timeout=turn_deadline_sec)
        except DeadlineExceededError:
            return "timeout", records, peer_commits, my_commits
        peer_commits[thief_message["step"]] = thief_message["commit"]

        _phase("VERIFYING")
        claim_response = thief_message.get("claim_response") or {}
        if claim_response.get("caught") is True:
            return "capture", records, peer_commits, my_commits
        if (thief_message.get("win_claim") or {}).get("type") == "survival":
            return "survival", records, peer_commits, my_commits

        last_thief_scent = thief_message.get("smell_grid") or {}
        _phase("WAITING_FOR_OPPONENT")
        step += 1

    return "survival", records, peer_commits, my_commits
