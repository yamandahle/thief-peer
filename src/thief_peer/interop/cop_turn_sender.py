"""Per-turn outbound calls to a real Cop peer, matching her actual tool
names/payload shapes (`tools/mcp_server.py`, `mcp_server_prd6.py`,
`mcp_server_prd9.py`) -- the same responsibility `peer/turn_sender.py`
has for a native Thief opponent, translated to her wire vocabulary. Her
`receive_commit`/`receive_reveal` accept this side's `h_commit`/move/hint
as-is; whether her end-of-match audit can *verify* them against her own
7-field commit envelope is a separate, known gap (this package's `__init__.py`).

Every per-round call that could mutate her state (commit/reveal,
barrier/capture claim-response) goes through as `retryable=False` --
`infra/mcp_client.py`'s own docstring has the full reasoning: a retried
reveal could land twice and fold the same evidence into her belief map
twice, corrupting a per-round Bayesian update that can't tell "applied
once" from "applied twice." `cop_send_final_reveal` is the one exception
(`retryable=True`, found necessary by a real batch of automated local
matches -- a fast run of many back-to-back games occasionally hit a
transient "connection refused" right as both processes finish their
round loops and this side calls hers): her own `receive_final_reveal`
just records the nonces/intents and reruns the audit against the exact
same trace log either way, so calling it twice with identical data is
provably harmless, unlike a per-round belief fold-in. `cop_request_scent_map`
is a pure read and stays retryable too.
"""

import time

from thief_peer.interop.cop_wire import deserialize_scent_from_cop


def cop_send_commit(transport, h_commit: str, deadline_sec: float) -> dict:
    # sent_at/deadline_at (her PRD 15, ch.8.4): added to her real
    # receive_commit's wire shape after this adapter was first built --
    # her own docstring says they're "logged by the callback, never
    # trusted (rule 9)", so this side only needs to send plausible values,
    # never anything she'd actually verify against.
    sent_at = time.time()
    return transport.call(
        "receive_commit",
        {"h_commit": h_commit, "sent_at": sent_at, "deadline_at": sent_at + deadline_sec},
        retryable=False,
    )


def cop_send_reveal(transport, move: str, hint_text: str, deadline_sec: float) -> dict:
    sent_at = time.time()
    return transport.call(
        "receive_reveal",
        {
            "move": {"type": "move", "direction": move},
            "hint_text": hint_text,
            "sent_at": sent_at,
            "deadline_at": sent_at + deadline_sec,
        },
        retryable=False,
    )


def cop_request_scent_map(transport) -> dict[str, float]:
    wire = transport.call("share_scent_map", {})
    return deserialize_scent_from_cop(wire)


def cop_send_final_reveal(transport, nonces: dict, intents: dict) -> dict:
    return transport.call("receive_final_reveal", {"nonces": nonces, "intents": intents})


def cop_send_barrier_declaration(transport, row: int, col: int) -> dict:
    return transport.call("receive_barrier_declaration", {"col": col, "row": row}, retryable=False)


def cop_send_capture_claim(
    transport, thief_row: int, thief_col: int, cop_row: int, cop_col: int, claimed_at_step: int
) -> dict:
    return transport.call(
        "receive_capture_claim",
        {
            "thief_col": thief_col,
            "thief_row": thief_row,
            "cop_col": cop_col,
            "cop_row": cop_row,
            "claimed_at_step": claimed_at_step,
        },
        retryable=False,
    )


def cop_send_capture_response(transport, confirmed: bool, true_thief_row: int, true_thief_col: int) -> dict:
    return transport.call(
        "receive_capture_response",
        {
            "confirmed": confirmed,
            "true_thief_col": true_thief_col,
            "true_thief_row": true_thief_row,
        },
        retryable=False,
    )
