"""interop/std_v1/series_runner.py tests: focused on `_row_for`'s scoring
table (spec Section 6, fixed by the rules, never negotiated) since
play_series itself is an end-to-end orchestration already covered
indirectly by the round-loop/audit/handshake unit tests -- a full fake
two-sided series would duplicate those without adding real coverage."""

import time
from unittest.mock import patch

from thief_peer.interop.std_v1.crypto import consensus_digest
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.roles import role_for_sub_game
from thief_peer.interop.std_v1.series_runner import (
    _SCORE_TABLE,
    _resolve_consensus,
    _resolve_consensus_with_watchdog,
    _row_for,
    _their_final_games_played,
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


def test_resolve_consensus_with_watchdog_returns_the_real_result_on_the_normal_path():
    exchange = StdExchange(poll_interval=0.01)
    digest = consensus_digest({"game_id": "A-vs-B", "game_uid": "u", "sub_games": []})
    exchange.record_audit({"sender": "police", "result_claim": "series_consensus", "records": [], "consensus_sha": digest})

    agreed, peer_digest = _resolve_consensus_with_watchdog(
        _StubTransport(), exchange, "thief", digest, 0.01, 1.0, all_clean=True, all_results_agreed=True,
    )

    assert agreed is True
    assert peer_digest == digest


def test_resolve_consensus_with_watchdog_fires_when_the_callee_hangs_past_its_own_ceiling():
    # yanell11, live: an outbound McpTransport.call() mid-flight when the
    # peer's own consensus envelope arrived inbound within the same few
    # seconds left the whole series stuck for 8+ minutes -- well past both
    # McpTransport's own per-call response_timeout_sec and
    # _resolve_consensus's own consensus_ceiling_sec. Neither of that
    # function's own internal bounds fired; the process had to be killed
    # by hand. Simulates that exact class of hang -- _resolve_consensus
    # itself blocks forever, ignoring its own ceiling entirely -- and
    # proves the watchdog still returns within a bounded time regardless.
    # Grace period shortened (same monkeypatch pattern std_v1_opponent.py's
    # own STD_V1_SHUTDOWN_GRACE_SECONDS test uses) so this test doesn't
    # actually wait 15 real seconds.
    def _hangs_forever(*args, **kwargs):
        time.sleep(3600)
        raise AssertionError("should never actually reach this point in the test")

    with (
        patch("thief_peer.interop.std_v1.series_runner._resolve_consensus", _hangs_forever),
        patch("thief_peer.interop.std_v1.series_runner._WATCHDOG_GRACE_SEC", 0.05),
    ):
        started = time.monotonic()
        agreed, peer_digest = _resolve_consensus_with_watchdog(
            _StubTransport(), StdExchange(poll_interval=0.01), "thief", "a" * 64,
            0.01, consensus_ceiling_sec=0.1, all_clean=True, all_results_agreed=True,
        )
        elapsed = time.monotonic() - started

    assert agreed is False
    assert peer_digest is None
    # Bounded by consensus_ceiling_sec + the watchdog's own grace period,
    # not by the 3600s the stuck callee is actually sleeping for.
    assert elapsed < 5.0


def test_their_final_games_played_adds_one_on_a_counted_series():
    # yanell11, live: declared 1 on the wire (their own prior count), so a
    # counted game should file 2 for them -- mirroring the +1 already
    # applied to our own side.
    assert _their_final_games_played(1, is_counted=True) == 2


def test_their_final_games_played_leaves_it_raw_on_a_friendly():
    # No +1 for a friendly -- matches the agreed wire convention exactly
    # ("the report adds +1 for a counted game, never for a friendly").
    assert _their_final_games_played(1, is_counted=False) == 1


def test_their_final_games_played_leaves_none_as_none_even_when_counted():
    # A peer that never declared a value at all is a real fact worth
    # keeping distinct from an explicitly-declared zero -- there is
    # nothing to add 1 to.
    assert _their_final_games_played(None, is_counted=True) is None


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
