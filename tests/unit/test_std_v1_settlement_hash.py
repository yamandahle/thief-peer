"""interop/std_v1/settlement_hash.py tests -- yanell11's own settlement
hash dialect (aggregate + trimmed rows, spaced separators), built on top
of this repo's own real report.py/audit.py functions rather than
hand-typed fixtures, so a real behavior change in either would break
this test too."""

from thief_peer.interop.std_v1.audit import build_sub_game_row
from thief_peer.interop.std_v1.report import final_result
from thief_peer.interop.std_v1.settlement_hash import (
    build_aggregate,
    build_settlement_rows,
    settlement_hash,
)

X, OPP = "X", "opponent"


def _six_zero_series():
    rows = []
    for n in range(1, 7):
        if n % 2 == 1:
            rows.append(build_sub_game_row(n, "capture", {X: "police", OPP: "thief"}, {X: 20, OPP: 5}, X))
        else:
            rows.append(build_sub_game_row(n, "survival", {X: "thief", OPP: "police"}, {X: 10, OPP: 5}, X))
    return rows


def test_build_aggregate_matches_yanell11s_worked_example_exactly():
    rows = _six_zero_series()
    fr = final_result(rows, X, OPP)

    assert build_aggregate(fr) == {
        "total_score": {"X": 90, "opponent": 30},
        "sub_games_won": {"X": 6, "opponent": 0},
        "ties": 0,
        "winner_group": "X",
        "series_tie": False,
    }


def test_build_aggregate_drops_our_own_extra_fields():
    fr = final_result(_six_zero_series(), X, OPP)
    aggregate = build_aggregate(fr)
    assert "tokens_total_series" not in aggregate
    assert "games_played_including_this" not in aggregate
    assert "diversity_reward_applied" not in aggregate
    assert set(aggregate.keys()) == {"total_score", "sub_games_won", "ties", "winner_group", "series_tie"}


def test_build_settlement_rows_trims_to_exactly_five_fields():
    rows = _six_zero_series()
    trimmed = build_settlement_rows(rows)
    assert len(trimmed) == 6
    for row in trimmed:
        assert set(row.keys()) == {"sub_game_number", "roles", "result", "winner_group", "score"}


def test_settlement_hash_uses_spaced_separators_not_the_compact_form():
    rows = _six_zero_series()
    fr = final_result(rows, X, OPP)
    # Same inputs, sha256 is deterministic -- re-deriving the canonical
    # string directly (spaced separators) must reproduce the same digest
    # settlement_hash() computed internally.
    import hashlib
    import json

    obj = {
        "game_id": "X-vs-opponent",
        "aggregate": build_aggregate(fr),
        "sub_games": build_settlement_rows(rows),
    }
    expected = hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(", ", ": ")).encode("utf-8")
    ).hexdigest()

    assert settlement_hash("X-vs-opponent", fr, rows) == expected


def test_settlement_hash_is_a_real_64_hex_digest():
    rows = _six_zero_series()
    fr = final_result(rows, X, OPP)
    h = settlement_hash("X-vs-opponent", fr, rows)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
