"""domain/game_ids.py tests (PRD_6 §3): deterministic identifiers stitching
the four report artifacts together (PLAN.md §5)."""

from thief_peer.domain.game_ids import derive_game_id, derive_game_uid


def test_derive_game_id_is_human_readable_and_deterministic():
    a = derive_game_id("Segal-Police-Team", "Segal-Thief-Team")
    b = derive_game_id("Segal-Police-Team", "Segal-Thief-Team")

    assert a == b
    assert "segal-police-team" in a
    assert "segal-thief-team" in a
    assert "-vs-" in a


def test_derive_game_id_distinguishes_the_two_group_orders():
    forward = derive_game_id("group-a", "group-b")
    reverse = derive_game_id("group-b", "group-a")
    assert forward != reverse


def test_derive_game_uid_stitches_game_id_and_sub_game_number():
    game_id = derive_game_id("group-a", "group-b")
    uid1 = derive_game_uid(game_id, 1)
    uid2 = derive_game_uid(game_id, 2)

    assert uid1 != uid2
    assert game_id in uid1
    assert "g01" in uid1
    assert "g02" in uid2


def test_derive_game_uid_zero_pads_single_digit_sub_game_numbers():
    uid = derive_game_uid("some-game", 3)
    assert uid == "some-game_g03"
