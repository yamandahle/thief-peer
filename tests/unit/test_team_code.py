"""shared/team_code.py tests (rule 45 [MUST]): a unique 8-character team
code, no spaces -- a separate concept from --group-name."""

import pytest

from thief_peer.exceptions import ConfigError
from thief_peer.shared.team_code import validate_team_code


def test_validate_team_code_accepts_a_real_8_character_code():
    validate_team_code("ABCD1234")  # must not raise


def test_validate_team_code_rejects_too_short():
    with pytest.raises(ConfigError, match="8 characters"):
        validate_team_code("ABC123")


def test_validate_team_code_rejects_too_long():
    with pytest.raises(ConfigError, match="8 characters"):
        validate_team_code("ABCD12345")


def test_validate_team_code_rejects_a_space_even_at_8_characters():
    with pytest.raises(ConfigError, match="spaces"):
        validate_team_code("ABC 1234")


def test_validate_team_code_rejects_an_empty_string():
    with pytest.raises(ConfigError, match="8 characters"):
        validate_team_code("")


def test_validate_team_code_rejects_a_tab_or_newline_not_just_a_plain_space():
    with pytest.raises(ConfigError, match="spaces"):
        validate_team_code("ABC\t1234")


def test_validate_team_code_never_truncates_or_strips_silently():
    # A common footgun for this kind of check -- confirm it actually
    # raises rather than quietly accepting a too-long code by truncating it.
    with pytest.raises(ConfigError):
        validate_team_code("ABCDEFGHIJ")
