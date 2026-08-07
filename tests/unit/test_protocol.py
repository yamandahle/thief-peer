"""domain/protocol.py tests (PRD_8 §2.2, §3). The two properties the whole
Ch.5 commit-reveal mechanism depends on: a reveal message never carries the
nonce (withheld until the end-of-match audit) and no wire message ever
carries a `position` key (ADR-8)."""

from thief_peer.domain.protocol import (
    build_audit_payload,
    build_commit_message,
    build_reveal_message,
)


def test_build_commit_message_carries_only_the_hash():
    message = build_commit_message(step=7, sender="thief", h_commit="deadbeef")

    assert message == {"step": 7, "sender": "thief", "h_commit": "deadbeef"}


def test_build_commit_message_never_carries_move_or_intent_or_nonce():
    message = build_commit_message(step=1, sender="thief", h_commit="abc123")

    assert "move" not in message
    assert "intent" not in message
    assert "nonce" not in message
    assert "position" not in message


def test_build_reveal_message_carries_move_hint_and_scent_but_never_nonce():
    message = build_reveal_message(
        step=7,
        sender="thief",
        hint="heading north",
        scent_grid={"3,4": 0.9},
        move="N",
        intent="truth",
    )

    assert message == {
        "step": 7,
        "sender": "thief",
        "hint": "heading north",
        "scent_grid": {"3,4": 0.9},
        "move": "N",
        "intent": "truth",
    }


def test_build_reveal_message_never_carries_nonce_or_position():
    message = build_reveal_message(
        step=1, sender="thief", hint="", scent_grid={}, move="STAY", intent="truth"
    )

    assert "nonce" not in message
    assert "position" not in message


def test_build_audit_payload_matches_the_submit_audit_tool_shape():
    records = [{"payload": {"state": "s", "move": "N", "intent": "truth", "nonce": "n"}, "commit": "c"}]

    payload = build_audit_payload(sender="thief", result_claim="survival", records=records)

    assert payload == {"sender": "thief", "result_claim": "survival", "records": records}
