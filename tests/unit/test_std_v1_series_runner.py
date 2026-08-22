"""interop/std_v1/series_runner.py tests: focused on `_row_for`'s scoring
table (spec Section 6, fixed by the rules, never negotiated) since
play_series itself is an end-to-end orchestration already covered
indirectly by the round-loop/audit/handshake unit tests -- a full fake
two-sided series would duplicate those without adding real coverage."""

from thief_peer.interop.std_v1.crypto import consensus_digest
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.roles import role_for_sub_game
from thief_peer.interop.std_v1.series_runner import (
    _SCORE_TABLE,
    _resolve_consensus,
    _row_for,
    _transport_for_role,
)


class _StubTransport:
    def call(self, name, payload):
        return {"acknowledged": True}


def test_resolve_consensus_confirms_when_the_peer_envelope_matches():
    exchange = StdExchange(poll_interval=0.01)
    digest = consensus_digest({"game_id": "A-vs-B", "game_uid": "u", "sub_games": []})
    exchange.record_audit({"sender": "police", "result_claim": "series_consensus", "records": [], "consensus_sha": digest})

    agreed, peer_digest = _resolve_consensus(
        _StubTransport(), exchange, "thief", digest, 0.01, 1.0, all_clean=True, all_results_agreed=True,
    )

    assert agreed is True
    assert peer_digest == digest


def test_resolve_consensus_never_raises_when_the_peer_envelope_never_arrives():
    # This is the exact bug found live: a clean 6/6 audited match still
    # crashed the whole series right here before this behavior existed,
    # so no report/email was ever produced despite nothing actually being
    # wrong with the match itself.
    exchange = StdExchange(poll_interval=0.01)

    agreed, peer_digest = _resolve_consensus(
        _StubTransport(), exchange, "thief", "a" * 64, 0.01, 0.05, all_clean=True, all_results_agreed=True,
    )

    assert agreed is False
    assert peer_digest is None


def test_resolve_consensus_never_raises_on_a_malformed_peer_envelope():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sender": "referee", "result_claim": "series_consensus", "records": [], "consensus_sha": "a" * 64})

    agreed, peer_digest = _resolve_consensus(
        _StubTransport(), exchange, "thief", "a" * 64, 0.01, 1.0, all_clean=True, all_results_agreed=True,
    )

    assert agreed is False
    assert peer_digest is None


def test_resolve_consensus_does_not_confirm_on_a_digest_mismatch():
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_audit({"sender": "police", "result_claim": "series_consensus", "records": [], "consensus_sha": "b" * 64})

    agreed, peer_digest = _resolve_consensus(
        _StubTransport(), exchange, "thief", "a" * 64, 0.01, 1.0, all_clean=True, all_results_agreed=True,
    )

    assert agreed is False
    assert peer_digest == "b" * 64


def test_transport_for_role_uses_the_one_transport_for_both_roles_when_unset():
    # Every existing single-URL opponent's behavior: transport_when_police
    # is None, so both roles dial the same transport.
    transport = _StubTransport()
    assert _transport_for_role("thief", transport, None) is transport
    assert _transport_for_role("police", transport, None) is transport


def test_transport_for_role_dials_the_second_transport_only_for_police():
    transport = _StubTransport()
    transport_when_police = _StubTransport()
    assert _transport_for_role("thief", transport, transport_when_police) is transport
    assert _transport_for_role("police", transport, transport_when_police) is transport_when_police


def test_role_for_sub_game_can_open_police_first_for_an_opponent_that_refuses_to_swap():
    # najamjad, live: their team is also unconditionally thief-first and
    # will not swap -- this repo accommodates by overriding natural_role
    # to "police" for that one opponent's config only.
    assert role_for_sub_game("police", 1) == "police"
    assert role_for_sub_game("police", 2) == "thief"
    assert role_for_sub_game("police", 3) == "police"


def test_row_for_capture_scores_20_5_police_thief_split():
    row = _row_for(1, my_role="police", end_reason="capture", tampered=False, my_group_id="A", their_group_id="B")
    assert row["score"] == {"A": 20, "B": 5}
    assert row["winner_group"] == "A"
    assert row["roles"] == {"A": "police", "B": "thief"}


def test_row_for_survival_scores_5_10_police_thief_split():
    row = _row_for(1, my_role="thief", end_reason="survival", tampered=False, my_group_id="A", their_group_id="B")
    assert row["score"] == {"A": 10, "B": 5}
    assert row["winner_group"] == "A"


def test_row_for_timeout_is_a_zeroed_tie():
    row = _row_for(1, my_role="thief", end_reason="timeout", tampered=False, my_group_id="A", their_group_id="B")
    assert row["score"] == {"A": 0, "B": 0}
    assert row["winner_group"] is None
    assert row["result"] == "timeout"


def test_row_for_tampered_forces_tamper_forfeit_regardless_of_end_reason():
    row = _row_for(1, my_role="thief", end_reason="capture", tampered=True, my_group_id="A", their_group_id="B")
    assert row["result"] == "tamper_forfeit"
    assert row["score"] == {"A": 0, "B": 0}
    assert row["winner_group"] is None


def test_score_table_covers_every_end_reason_and_tamper_forfeit():
    assert set(_SCORE_TABLE) == {"capture", "survival", "timeout", "technical_loss", "tamper_forfeit"}
    for outcome, points in _SCORE_TABLE.items():
        assert set(points) == {"police", "thief"}
