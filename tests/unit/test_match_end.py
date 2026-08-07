"""peer/match_end.py tests (PRD_8 §3). Pins the symmetric game_id fix found
while building this stage's live-match integration test: two independently-
built peers, each calling finalize_match with themselves as "group_name" and
the other as "opponent_group_name", must land on the identical game_id."""

from thief_peer.peer.match_end import finalize_match


class _SpyTransport:
    def call(self, tool_name, payload):
        assert tool_name == "submit_audit"
        return {"passed": True, "verified_steps": len(payload["payload"]["records"]), "failed_steps": []}


class _ExplodingTransport:
    def call(self, tool_name, payload):
        raise AssertionError("submit_audit must not be called on a technical loss")


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
