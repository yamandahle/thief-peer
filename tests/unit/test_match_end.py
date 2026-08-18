"""peer/match_end.py tests (PRD_8 §3; post-Stage-8 mutual-audit fix).

Pins the symmetric game_id fix found while building the Stage-8 live-match
integration test (order-sensitive derive_game_id), and the mutual-audit fix
found afterward: finalize_match used to only ever submit this peer's own
records to the opponent's `submit_audit` (getting audited BY them) without
ever pulling and auditing the opponent's own revealed log (auditing THEM) --
rules 19/36 require both directions, not one. `opponent_audit` failing (this
peer catches the opponent lying) or `self_audit` failing (the opponent
catches this peer lying) must each override the natural game-outcome winner,
per rule 19's "any hash mismatch = automatic 0 to the forging team"."""

import pytest

from thief_peer.domain.crypto import CommitReveal
from thief_peer.exceptions import ConfigError
from thief_peer.peer.match_end import finalize_match


def _sealed_record(state="s", move="N", intent="truth"):
    payload = {"state": state, "move": move, "intent": intent}
    sealed = CommitReveal.seal(payload)
    return {"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]}


class _SpyTransport:
    def __init__(self, opponent_records=None, self_audit_result=None):
        self._opponent_records = opponent_records if opponent_records is not None else []
        self._self_audit_result = self_audit_result or {
            "passed": True,
            "verified_steps": 0,
            "failed_steps": [],
        }

    def call(self, tool_name, payload):
        if tool_name == "submit_audit":
            return self._self_audit_result
        if tool_name == "get_revealed_records":
            return {"records": self._opponent_records}
        raise AssertionError(f"unexpected tool call: {tool_name}")


class _ExplodingTransport:
    def call(self, tool_name, payload):
        raise AssertionError(f"{tool_name} must not be called on a technical loss")


class _SpyGatekeeper:
    def execute(self, api_call, *args, **kwargs):
        return api_call(*args, **kwargs)


class _FakeGmailService:
    def users(self):
        return self

    def messages(self):
        return self

    def send(self, userId, body):  # noqa: N803 -- must match the real Gmail API's kwarg name
        return self

    def execute(self):
        return {"id": "fake-message-id"}


class _ConfigStub:
    def get(self, key, default=None):
        return default

    def require(self, key):
        raise AssertionError(f"unexpected require({key!r}) in this test")


def _finalize(tmp_path, monkeypatch, **overrides):
    monkeypatch.setattr("thief_peer.peer.match_end.canonical_terms", lambda config: {"grid_size": 7})
    kwargs = {
        "group_name": "Thief-Team-A",
        "opponent_group_name": "Thief-Team-B",
        "end_reason": "survived",
        "records": [],
        "config": _ConfigStub(),
        "transport": _SpyTransport(),
        "gatekeeper": _SpyGatekeeper(),
        "email_service": _FakeGmailService(),
        "recipient": "grader@example.com",
        "results_dir": tmp_path,
        "sub_game_number": 1,
        "num_sub_games": 1,
    }
    kwargs.update(overrides)
    return finalize_match(**kwargs)


def test_both_sides_compute_the_identical_game_id_regardless_of_call_order(tmp_path, monkeypatch):
    result_a = _finalize(
        tmp_path / "a",
        monkeypatch,
        group_name="Thief-Team-A",
        opponent_group_name="Thief-Team-B",
    )
    result_b = _finalize(
        tmp_path / "b",
        monkeypatch,
        group_name="Thief-Team-B",
        opponent_group_name="Thief-Team-A",
    )

    assert result_a["game_id"] == result_b["game_id"]
    assert result_a["game_uid"] == result_b["game_uid"]


def test_raises_a_clear_config_error_instead_of_a_bare_stopiteration_on_self_play(
    tmp_path, monkeypatch
):
    """A self-vs-self warm-up (own paired Cop, same real group id on both
    sides) used to collapse roles/score/github_commit/tokens/log_files --
    all keyed {group_name: ..., opponent_group_name: ...} -- into a single
    dict entry, then crash deep inside score_sub_game with a bare
    StopIteration only after the whole match had already played out."""
    with pytest.raises(ConfigError, match="identical"):
        _finalize(tmp_path, monkeypatch, group_name="yamanagh", opponent_group_name="yamanagh")


def test_winner_is_self_on_survival(tmp_path, monkeypatch):
    result = _finalize(tmp_path, monkeypatch, end_reason="survived")
    assert result["final_result"]["winner_group"] == "Thief-Team-A"


def test_winner_is_opponent_on_technical_loss_and_audit_is_skipped(tmp_path, monkeypatch):
    result = _finalize(
        tmp_path, monkeypatch, end_reason="technical_loss", transport=_ExplodingTransport()
    )
    assert result["final_result"]["winner_group"] == "Thief-Team-B"
    assert result["audit"]["passed"] is False


def test_winner_is_opponent_when_captured(tmp_path, monkeypatch):
    result = _finalize(tmp_path, monkeypatch, end_reason="captured")
    assert result["final_result"]["winner_group"] == "Thief-Team-B"


def test_actively_pulls_and_audits_the_opponents_own_revealed_records(tmp_path, monkeypatch):
    """The core of the fix: finalize_match must call get_revealed_records
    on the opponent and run a real local audit_records() over what comes
    back -- not just submit its own records and stop there."""
    opponent_records = [_sealed_record(state="s0"), _sealed_record(state="s1")]
    transport = _SpyTransport(opponent_records=opponent_records)

    result = _finalize(tmp_path, monkeypatch, end_reason="survived", transport=transport)

    assert result["audit"]["opponent_audited_by_me"]["passed"] is True
    assert result["audit"]["opponent_audited_by_me"]["verified_steps"] == 2
    assert result["audit"]["self_audited_by_opponent"]["passed"] is True
    assert result["audit"]["passed"] is True


def test_catching_the_opponent_lying_overrides_the_natural_winner(tmp_path, monkeypatch):
    tampered = _sealed_record(state="s0")
    tampered["payload"]["move"] = "S"  # tampered after sealing
    transport = _SpyTransport(opponent_records=[tampered])

    # Natural game outcome says "captured" (opponent should win) -- but this
    # peer independently caught the opponent's revealed log failing its own
    # commit hash, which must win regardless (rule 19: automatic).
    result = _finalize(tmp_path, monkeypatch, end_reason="captured", transport=transport)

    assert result["audit"]["opponent_audited_by_me"]["passed"] is False
    assert result["audit"]["passed"] is False
    assert result["final_result"]["winner_group"] == "Thief-Team-A"


def test_being_caught_lying_by_the_opponent_overrides_the_natural_winner(tmp_path, monkeypatch):
    transport = _SpyTransport(
        self_audit_result={"passed": False, "verified_steps": 3, "failed_steps": [1]}
    )

    # Natural game outcome says "survived" (this peer should win) -- but the
    # opponent's own audit of this peer's log found a mismatch, which must
    # cost this peer the win regardless (rule 19: automatic, no appeal).
    result = _finalize(tmp_path, monkeypatch, end_reason="survived", transport=transport)

    assert result["audit"]["self_audited_by_opponent"]["passed"] is False
    assert result["audit"]["passed"] is False
    assert result["final_result"]["winner_group"] == "Thief-Team-B"


def test_repos_are_included_in_group_1s_own_entry_when_supplied(tmp_path, monkeypatch):
    """Rule 49 ("four links in both teams' JSON"): report this peer's own
    known repo URLs -- never invented for the opponent's side, which has no
    wire channel to learn (same honest limitation the Cop repo's own
    orchestrator_end_of_game.py docstring documents)."""
    repos = {"thief": "https://github.com/yamandahle/thief-peer", "cop": "https://github.com/x/y"}

    result = _finalize(tmp_path, monkeypatch, repos=repos)

    assert result["groups"]["group_1"]["repos"] == repos
    assert "repos" not in result["groups"]["group_2"]


def test_repos_defaults_to_empty_when_not_supplied(tmp_path, monkeypatch):
    result = _finalize(tmp_path, monkeypatch)

    assert result["groups"]["group_1"]["repos"] == {}


def test_is_counted_is_passed_through_to_write_and_send(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "thief_peer.peer.match_end.write_and_send",
        lambda *args, **kwargs: captured.update(kwargs),
    )

    _finalize(tmp_path, monkeypatch, is_counted=False)

    assert captured["is_counted"] is False


def test_is_counted_defaults_to_true(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "thief_peer.peer.match_end.write_and_send",
        lambda *args, **kwargs: captured.update(kwargs),
    )

    _finalize(tmp_path, monkeypatch)

    assert captured["is_counted"] is True


def _captured_sub_game_entry(tmp_path, monkeypatch, **overrides):
    captured = {}
    monkeypatch.setattr(
        "thief_peer.peer.match_end.write_and_send",
        lambda match_result, *args, **kwargs: captured.update(match_result),
    )
    _finalize(tmp_path, monkeypatch, **overrides)
    return captured["sub_game_entry"]


def test_sub_game_entry_maps_survived_to_the_survival_result_value(tmp_path, monkeypatch):
    entry = _captured_sub_game_entry(tmp_path, monkeypatch, end_reason="survived")

    assert entry["result"] == "survival"
    assert entry["winner_group"] == "Thief-Team-A"
    # Table 2 (book §3.5, p.22): scored by role, not by winner -- the
    # thief (Thief-Team-A) gets survival_thief, the cop gets survival_cop.
    assert entry["score"] == {"Thief-Team-A": 10, "Thief-Team-B": 5}
    assert entry["tie"] is False
    assert entry["audit"]["tampered"] is False


def test_sub_game_entry_maps_captured_to_the_capture_result_value(tmp_path, monkeypatch):
    entry = _captured_sub_game_entry(tmp_path, monkeypatch, end_reason="captured")

    assert entry["result"] == "capture"
    assert entry["winner_group"] == "Thief-Team-B"
    # Captured thief (Thief-Team-A) still scores capture_thief, not 0.
    assert entry["score"] == {"Thief-Team-A": 5, "Thief-Team-B": 20}


def test_sub_game_entry_maps_technical_loss_to_timeout_not_a_missing_enum_value(
    tmp_path, monkeypatch
):
    # Book's `result` enum has no slot for a protocol/deadline failure --
    # documented Academic-Freedom reading (README.md): technical_loss ->
    # "timeout", since every technical-loss path here stems from a
    # deadline/protocol-timing failure, not a rules violation.
    entry = _captured_sub_game_entry(
        tmp_path, monkeypatch, end_reason="technical_loss", transport=_ExplodingTransport()
    )

    assert entry["result"] == "timeout"
    assert entry["audit"]["log_verified"] is False


def test_sub_game_entry_marks_tamper_forfeit_when_the_audit_overrides_the_winner(
    tmp_path, monkeypatch
):
    tampered = _sealed_record(state="s0")
    tampered["payload"]["move"] = "S"  # tampered after sealing
    transport = _SpyTransport(opponent_records=[tampered])

    entry = _captured_sub_game_entry(
        tmp_path, monkeypatch, end_reason="captured", transport=transport
    )

    assert entry["result"] == "tamper_forfeit"
    assert entry["winner_group"] == "Thief-Team-A"
    assert entry["audit"]["tampered"] is True


def test_sub_game_entry_maps_max_moves_reached_to_survival_not_timeout(tmp_path, monkeypatch):
    # Table 2 (book §3.5, p.22) has no "timeout" row -- reaching the move
    # cap uncaptured is exactly its "survival" condition, regardless of
    # which check noticed it (docs/TodoCloseGaps.md #1).
    entry = _captured_sub_game_entry(tmp_path, monkeypatch, end_reason="max_moves_reached")

    assert entry["result"] == "survival"
    assert entry["winner_group"] == "Thief-Team-A"
    assert entry["score"] == {"Thief-Team-A": 10, "Thief-Team-B": 5}


class _ScoringConfigStub:
    """Unlike _ConfigStub, actually answers scoring.* reads -- proves the
    values genuinely come from config, not just the hardcoded fallback."""

    def get(self, key, default=None):
        values = {
            "scoring.capture_cop": 200,
            "scoring.capture_thief": 50,
            "scoring.survival_cop": 3,
            "scoring.survival_thief": 99,
        }
        return values.get(key, default)

    def require(self, key):
        raise AssertionError(f"unexpected require({key!r}) in this test")


def test_sub_game_entry_score_is_actually_read_from_the_shared_scoring_config(
    tmp_path, monkeypatch
):
    entry = _captured_sub_game_entry(
        tmp_path, monkeypatch, end_reason="captured", config=_ScoringConfigStub()
    )

    assert entry["score"] == {"Thief-Team-A": 50, "Thief-Team-B": 200}


class _LeagueParamsConfigStub:
    """docs/TodoCloseGaps.md #4: proves league params are genuinely read
    from config, not just defaulted to None."""

    def get(self, key, default=None):
        values = {
            "network_and_league.diversity_reward": 10,
            "network_and_league.min_games_to_pass": 2,
            "network_and_league.max_games_per_team": 10,
            "network_and_league.token_budget_per_series": 200000,
        }
        return values.get(key, default)

    def require(self, key):
        raise AssertionError(f"unexpected require({key!r}) in this test")


def _captured_match_result(tmp_path, monkeypatch, **overrides):
    captured = {}
    monkeypatch.setattr(
        "thief_peer.peer.match_end.write_and_send",
        lambda match_result, *args, **kwargs: captured.update(match_result),
    )
    _finalize(tmp_path, monkeypatch, **overrides)
    return captured


def test_match_result_carries_league_params_read_from_config(tmp_path, monkeypatch):
    match_result = _captured_match_result(
        tmp_path, monkeypatch, config=_LeagueParamsConfigStub()
    )

    assert match_result["league_params"] == {
        "diversity_reward": 10,
        "min_games_to_pass": 2,
        "max_games_per_team": 10,
        "token_budget_per_series": 200000,
    }


def test_match_result_league_params_default_to_none_when_config_lacks_the_section(
    tmp_path, monkeypatch
):
    match_result = _captured_match_result(tmp_path, monkeypatch)

    assert match_result["league_params"] == {
        "diversity_reward": None,
        "min_games_to_pass": None,
        "max_games_per_team": None,
        "token_budget_per_series": None,
    }


def test_sub_game_entry_carries_github_commit_and_started_at_through(tmp_path, monkeypatch):
    entry = _captured_sub_game_entry(
        tmp_path,
        monkeypatch,
        started_at="2026-01-01T00:00:00+00:00",
        our_github_commit="abc123",
        opponent_github_commit="def456",
    )

    assert entry["started_at"] == "2026-01-01T00:00:00+00:00"
    assert entry["github_commit"] == {"Thief-Team-A": "abc123", "Thief-Team-B": "def456"}
