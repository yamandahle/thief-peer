"""std_v1/identity.py tests."""

from thief_peer.interop.std_v1.identity import build_identity


def test_build_identity_carries_every_required_field():
    identity = build_identity(
        group_id="dev-team", group_name="Dev Team", members=["a", "b"],
        repos={"cop": "url1", "thief": "url2"}, mcp_servers={"cop": "http://x"},
        llm_model="claude-sonnet-5",
    )
    assert identity["group_id"] == "dev-team"
    assert identity["group_name"] == "Dev Team"
    assert identity["members"] == ["a", "b"]
    assert identity["repos"] == {"cop": "url1", "thief": "url2"}
    assert identity["llm_model"] == "claude-sonnet-5"
    assert identity["git_commit_hash"] == identity["github_commit"]


def test_build_identity_copies_mutable_inputs():
    members = ["a"]
    identity = build_identity(group_id="g", group_name="G", members=members, repos={}, mcp_servers={}, llm_model="m")
    members.append("b")
    assert identity["members"] == ["a"]


def test_build_identity_omits_scent_model_lock_when_not_given():
    identity = build_identity(group_id="g", group_name="G", members=[], repos={}, mcp_servers={}, llm_model="m")
    assert "scent_model_lock" not in identity


def test_build_identity_includes_scent_model_lock_when_given():
    lock = {"family": "scent_model", "name": "multiplicative_book_v1"}
    identity = build_identity(
        group_id="g", group_name="G", members=[], repos={}, mcp_servers={}, llm_model="m",
        scent_model_lock=lock,
    )
    assert identity["scent_model_lock"] == lock
