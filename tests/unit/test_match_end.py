"""peer/match_end.py tests (PRD_8 §3; post-Stage-8 mutual-audit fix)."""

import json

from thief_peer.domain.crypto import CommitReveal
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
    def __init__(self):
        self.call_count = 0

    def execute(self, api_call, *args, **kwargs):
        self.call_count += 1
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
    _SCORING = {
        "scoring.capture_thief": 5,
        "scoring.capture_cop": 20,
        "scoring.survival_thief": 10,
        "scoring.survival_cop": 5,
        "board_and_agents.grid_size": 7,
        "network_and_league.min_games_to_pass": 2,
    }

    def get(self, key, default=None):
        return self._SCORING.get(key, default)

    def require(self, key):
        if key not in self._SCORING:
            raise AssertionError(f"unexpected require({key!r}) in this test")
        return self._SCORING[key]


def _finalize(tmp_path, monkeypatch, **overrides):
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
    # Rule 19's actual "iron law": the forging team's SCORE is 0, not just
    # the winner label -- a "captured" outcome would normally give the
    # opponent (the forger here) 20 points; they get 0 instead.
    assert result["final_result"]["total_score"]["Thief-Team-B"] == 0
    assert result["final_result"]["total_score"]["Thief-Team-A"] == 5  # honest side keeps its earned points


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
    # Same iron law, the other direction: a "survived" outcome would
    # normally give this peer (the forger here) 10 points; 0 instead.
    assert result["final_result"]["total_score"]["Thief-Team-A"] == 0
    assert result["final_result"]["total_score"]["Thief-Team-B"] == 5  # honest side keeps its earned points


def test_both_sides_score_zero_when_both_audits_fail(tmp_path, monkeypatch):
    tampered = _sealed_record(state="s0")
    tampered["payload"]["move"] = "S"
    transport = _SpyTransport(
        opponent_records=[tampered],
        self_audit_result={"passed": False, "verified_steps": 1, "failed_steps": [0]},
    )

    result = _finalize(tmp_path, monkeypatch, end_reason="captured", transport=transport)

    assert result["final_result"]["total_score"] == {"Thief-Team-A": 0, "Thief-Team-B": 0}


def test_repos_are_included_for_both_groups_in_declaration(tmp_path, monkeypatch):
    own = {"thief": "https://github.com/yamandahle/thief-peer", "cop": "https://github.com/x/y"}
    theirs = {"thief": "https://github.com/opp/thief", "cop": "https://github.com/opp/cop"}

    _finalize(tmp_path, monkeypatch, repos=own, opponent_repos=theirs)

    declaration_path = tmp_path / "declaration_thief-team-a-vs-thief-team-b.json"
    declaration = json.loads(declaration_path.read_text())
    groups = declaration["groups"]
    assert any(g["repos"] == own for g in groups.values())
    assert any(g["repos"] == theirs for g in groups.values())


def test_tokens_total_series_is_a_per_group_map(tmp_path, monkeypatch):
    result = _finalize(tmp_path, monkeypatch, tokens_own=42, tokens_opponent=7)
    series = result["final_result"]["tokens_total_series"]
    assert series == {"Thief-Team-A": 42, "Thief-Team-B": 7}


def test_repos_default_to_empty_when_not_supplied(tmp_path, monkeypatch):
    result = _finalize(tmp_path, monkeypatch)
    # stdout summary only — declaration repos checked via write_and_send in integration
    assert result["game_id"] == "thief-team-a-vs-thief-team-b"


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


def test_a_second_counted_game_against_the_same_opponent_is_not_double_counted(tmp_path, monkeypatch):
    # Rule 52 [FATAL]: exactly one counted game per opponent.
    result_1 = _finalize(tmp_path, monkeypatch, is_counted=True)
    assert result_1["league_status"]["counted_this_game"] is True
    assert result_1["league_status"]["distinct_opponents_played"] == 1

    result_2 = _finalize(tmp_path, monkeypatch, is_counted=True)  # same opponent, same results_dir
    assert result_2["league_status"]["counted_this_game"] is False
    assert result_2["league_status"]["distinct_opponents_played"] == 1  # unchanged -- no 2nd credit


def test_a_second_counted_game_still_writes_its_report_in_full(tmp_path, monkeypatch):
    # The league-bookkeeping guard must not cost the match its own
    # documentation -- only the extra league credit is withheld.
    _finalize(tmp_path, monkeypatch, is_counted=True)
    result_2 = _finalize(tmp_path, monkeypatch, is_counted=True)

    assert result_2["audit"]["passed"] is True
    assert (tmp_path / f"result_{result_2['game_id']}.json").exists()


def test_warm_up_games_can_repeat_freely_against_the_same_opponent(tmp_path, monkeypatch):
    # Rule 52's other half: uncounted warm-ups are explicitly allowed to
    # repeat, no warning, no guard triggered.
    result_1 = _finalize(tmp_path, monkeypatch, is_counted=False)
    result_2 = _finalize(tmp_path, monkeypatch, is_counted=False)

    assert result_1["league_status"]["counted_this_game"] is False
    assert result_2["league_status"]["counted_this_game"] is False
    assert result_2["league_status"]["distinct_opponents_played"] == 0  # never actually counted


def test_league_status_tracks_distinct_opponents_across_different_matches(tmp_path, monkeypatch):
    # Rule 31: a passing grade is measured on distinct opponents.
    result_1 = _finalize(
        tmp_path, monkeypatch, is_counted=True, opponent_group_name="Thief-Team-B"
    )
    assert result_1["league_status"]["distinct_opponents_played"] == 1

    result_2 = _finalize(
        tmp_path, monkeypatch, is_counted=True, opponent_group_name="Thief-Team-C"
    )
    assert result_2["league_status"]["distinct_opponents_played"] == 2


def test_league_status_reports_the_configured_minimum_to_pass(tmp_path, monkeypatch):
    result = _finalize(tmp_path, monkeypatch)
    assert result["league_status"]["min_games_to_pass"] == _ConfigStub._SCORING.get(
        "network_and_league.min_games_to_pass"
    )


def test_a_second_counted_game_prints_a_rule_52_warning(tmp_path, monkeypatch, capsys):
    _finalize(tmp_path, monkeypatch, is_counted=True)
    capsys.readouterr()  # discard the first match's own output
    _finalize(tmp_path, monkeypatch, is_counted=True)

    printed = capsys.readouterr().out
    assert "Rule 52" in printed
    assert "already recorded" in printed


def test_a_two_sub_game_series_only_emails_once_on_the_last_sub_game(tmp_path, monkeypatch):
    # Book ch.9.4: result_<game_id>.json is the summary for the WHOLE
    # series, sent once -- not once per sub-game. Both calls share the
    # same results_dir (real cross-process persistence) and the same
    # Gatekeeper (to count total email attempts across both).
    gatekeeper = _SpyGatekeeper()

    result_1 = _finalize(
        tmp_path, monkeypatch, sub_game_number=1, num_sub_games=2,
        end_reason="captured", gatekeeper=gatekeeper,
    )
    assert gatekeeper.call_count == 0  # not the last sub-game yet

    result_2 = _finalize(
        tmp_path, monkeypatch, sub_game_number=2, num_sub_games=2,
        end_reason="survived", gatekeeper=gatekeeper,
    )
    assert gatekeeper.call_count == 1  # the series' last sub-game

    # Sub-game 1: captured -> Thief-Team-B (opponent) is the natural winner
    # in _WINNER_IS_OPPONENT, scoring 5/20. Sub-game 2: survived -> this
    # side wins, 10/5. Real series total: A=15, B=25.
    assert result_1["final_result"]["total_score"] == {"Thief-Team-A": 5, "Thief-Team-B": 20}
    assert result_2["final_result"]["total_score"] == {"Thief-Team-A": 15, "Thief-Team-B": 25}

    on_disk = json.loads((tmp_path / "result_thief-team-a-vs-thief-team-b.json").read_text())
    assert [sg["sub_game_number"] for sg in on_disk["sub_games"]] == [1, 2]
    assert on_disk["final_result"]["total_score"] == {"Thief-Team-A": 15, "Thief-Team-B": 25}
    assert on_disk["final_result"]["winner_group"] == "Thief-Team-B"
