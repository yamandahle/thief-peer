"""Per-sub-game and per-series scoring (report schema's `final_result`).
Table 2 (book §3.5 "Win Conditions and Scoring", printed p.22) scores
**by role**, not by winner/loser: the cop and the thief each get their
own value for the same outcome, and the book's own text calls out the
deliberately "broken symmetry" -- capture rewards the cop most, survival
rewards the thief most. A captured thief still scores `capture_thief`
points, not zero. Only technical loss (a crash, a deadline exceeded, or
proven cryptographic forgery -- Table 2 groups all three into one row)
zeroes both sides.
"""


def score_sub_game(result: str, roles: dict[str, str], scoring: dict) -> dict:
    """`result` is one of "capture"/"survival"/"timeout"/"tamper_forfeit"
    (`peer/match_end.py`'s `_RESULT_VALUE`/audit-override mapping).
    `roles` maps each group name to "thief" or "cop" for this sub-game.
    `scoring` carries the negotiated `scoring.*` config values (capture_cop,
    capture_thief, survival_cop, survival_thief)."""
    cop = next(group for group, role in roles.items() if role == "cop")
    thief = next(group for group, role in roles.items() if role == "thief")
    if result == "capture":
        return {cop: scoring["capture_cop"], thief: scoring["capture_thief"]}
    if result == "survival":
        return {cop: scoring["survival_cop"], thief: scoring["survival_thief"]}
    return {cop: 0, thief: 0}  # technical loss / tamper forfeit -- Table 2's single 0/0 row


def aggregate_series(sub_games: list[dict], group_a: str, group_b: str) -> dict:
    """Recomputed from scratch over the full `sub_games` array every call
    (never incrementally patched), matching the real Cop peer's own
    reference implementation -- avoids drift from a stale running total.
    """
    total_score = {group_a: 0, group_b: 0}
    sub_games_won = {group_a: 0, group_b: 0}
    ties = 0
    for sg in sub_games:
        for team, pts in sg["score"].items():
            total_score[team] = total_score.get(team, 0) + pts
        if sg["tie"]:
            ties += 1
        elif sg["winner_group"]:
            sub_games_won[sg["winner_group"]] = sub_games_won.get(sg["winner_group"], 0) + 1

    if total_score[group_a] == total_score[group_b]:
        winner_group, series_tie = None, True
    else:
        winner_group = group_a if total_score[group_a] > total_score[group_b] else group_b
        series_tie = False

    return {
        "total_score": total_score,
        "sub_games_won": sub_games_won,
        "ties": ties,
        "winner_group": winner_group,
        "series_tie": series_tie,
        "tokens_total_series": {group_a: None, group_b: None},
    }
