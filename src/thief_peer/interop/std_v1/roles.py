"""Role alternation for std_v1 (spec Section 6/10 [MATCH]): odd sub-games
(1,3,5) play the natural role, even sub-games (2,4,6) the opposite. Part
of every canonical consensus row (Section 11's `roles` field), so it
must actually alternate for the hashed digest to have any chance of
matching a spec-compliant opponent's own digest.
"""

from __future__ import annotations

_OPPOSITE = {"thief": "police", "police": "thief"}


def opposite_role(role: str) -> str:
    return _OPPOSITE[role]


def role_for_sub_game(natural_role: str, sub_game_number: int) -> str:
    return natural_role if sub_game_number % 2 == 1 else opposite_role(natural_role)
