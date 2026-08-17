from thief_peer.interop.std_v1.roles import opposite_role, role_for_sub_game


def test_opposite_role_flips():
    assert opposite_role("thief") == "police"
    assert opposite_role("police") == "thief"


def test_role_for_sub_game_alternates_starting_from_natural():
    assert role_for_sub_game("thief", 1) == "thief"
    assert role_for_sub_game("thief", 2) == "police"
    assert role_for_sub_game("thief", 3) == "thief"
    assert role_for_sub_game("thief", 6) == "police"
    assert role_for_sub_game("police", 1) == "police"
    assert role_for_sub_game("police", 2) == "thief"
