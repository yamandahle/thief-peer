"""Per-sub-game and per-series scoring (report schema's `final_result`).
No numeric point formula is specified anywhere in the rulebook excerpts
available to us -- the simplest scheme consistent with `sub_games_won`
(winner scores 1, loser 0, a tie scores 0/0) is used, documented as a
judgment call in README.md alongside the other Academic-Freedom entries.
"""


def score_sub_game(winner_group: str | None, group_a: str, group_b: str) -> dict:
    if winner_group is None:
        return {group_a: 0, group_b: 0}
    loser = group_b if winner_group == group_a else group_a
    return {winner_group: 1, loser: 0}


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
