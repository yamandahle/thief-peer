"""Wire message builders (PRD_8 §2.2, §3): the book's Figure 6 literal
two-message-per-round shape -- Commit (hash only) and Reveal (move+hint,
nonce withheld until the end-of-match audit) are two separate payloads,
never bundled into one. Plain dict builders, matching `peer/sealing.py` and
`domain/negotiation.py`'s existing convention, not dataclasses. Neither
message ever carries a `position` key (ADR-8) or the sealing nonce.
"""


def build_commit_message(step: int, sender: str, h_commit: str) -> dict:
    return {"step": step, "sender": sender, "h_commit": h_commit}


def build_reveal_message(
    step: int, sender: str, hint: str, scent_grid: dict[str, float], move: str, intent: str
) -> dict:
    return {
        "step": step,
        "sender": sender,
        "hint": hint,
        "scent_grid": scent_grid,
        "move": move,
        "intent": intent,
    }


def build_audit_payload(sender: str, result_claim: str, records: list[dict]) -> dict:
    return {"sender": sender, "result_claim": result_claim, "records": records}
