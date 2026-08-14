"""Per-turn outbound calls to a real Cop peer, matching her actual tool
names/payload shapes (`tools/mcp_server.py`, `mcp_server_prd6.py`,
`mcp_server_prd9.py`) -- the same responsibility `peer/turn_sender.py`
has for a native Thief opponent, translated to her wire vocabulary. Her
`receive_commit`/`receive_reveal` accept this side's `h_commit`/move/hint
as-is; whether her end-of-match audit can *verify* them against her own
7-field commit envelope is a separate, known gap (this package's `__init__.py`).

Every call here that could mutate her state (commit/reveal/final-reveal,
barrier/capture claim-response) goes through as `retryable=False` --
`infra/mcp_client.py`'s own docstring has the full reasoning: a retried
reveal could land twice and fold the same evidence into her belief map
twice. `cop_request_scent_map` is a pure read and stays retryable.
"""

from thief_peer.interop.cop_wire import deserialize_scent_from_cop


def cop_send_commit(transport, h_commit: str) -> dict:
    return transport.call("receive_commit", {"h_commit": h_commit}, retryable=False)


def cop_send_reveal(transport, move: str, hint_text: str) -> dict:
    return transport.call(
        "receive_reveal",
        {"move": {"type": "move", "direction": move}, "hint_text": hint_text},
        retryable=False,
    )


def cop_request_scent_map(transport) -> dict[str, float]:
    wire = transport.call("share_scent_map", {})
    return deserialize_scent_from_cop(wire)


def cop_send_final_reveal(transport, nonces: dict, intents: dict) -> dict:
    return transport.call(
        "receive_final_reveal", {"nonces": nonces, "intents": intents}, retryable=False
    )


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
