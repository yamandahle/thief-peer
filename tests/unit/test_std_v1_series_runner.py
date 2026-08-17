"""interop/std_v1/series_runner.py tests: focused on `_row_for`'s scoring
table (spec Section 6, fixed by the rules, never negotiated) since
play_series itself is an end-to-end orchestration already covered
indirectly by the round-loop/audit/handshake unit tests -- a full fake
two-sided series would duplicate those without adding real coverage."""

from thief_peer.interop.std_v1.series_runner import _SCORE_TABLE, _row_for


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
