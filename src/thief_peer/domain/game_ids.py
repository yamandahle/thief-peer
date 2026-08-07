"""Deterministic game identifiers (PRD_6 §3): a human-readable `game_id`
from the two group names, and a per-sub-game `game_uid` stitching the four
report artifacts together (declaration/config/log/result, `PLAN.md` §5).
"""


def derive_game_id(group_a: str, group_b: str) -> str:
    return f"{_slug(group_a)}-vs-{_slug(group_b)}"


def derive_game_uid(game_id: str, sub_game_number: int) -> str:
    return f"{game_id}_g{sub_game_number:02d}"


def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-")
