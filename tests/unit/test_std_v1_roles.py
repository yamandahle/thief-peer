"""interop/std_v1/roles.py tests: spec Section 6/10 [MATCH] role
alternation -- odd sub-games play the natural role, even ones the
opposite. Part of every canonical consensus row, so getting the parity
backwards would desync the hashed digest against any spec-compliant peer."""

import pytest

from thief_peer.interop.std_v1.roles import opposite_role, role_for_sub_game


def test_opposite_role_flips_thief_and_police():
    assert opposite_role("thief") == "police"
    assert opposite_role("police") == "thief"


def test_opposite_role_rejects_an_unknown_role():
    with pytest.raises(KeyError):
        opposite_role("bystander")


@pytest.mark.parametrize("sub_game_number", [1, 3, 5])
def test_role_for_sub_game_is_natural_on_odd_sub_games(sub_game_number):
    assert role_for_sub_game("thief", sub_game_number) == "thief"


@pytest.mark.parametrize("sub_game_number", [2, 4, 6])
def test_role_for_sub_game_is_opposite_on_even_sub_games(sub_game_number):
    assert role_for_sub_game("thief", sub_game_number) == "police"
