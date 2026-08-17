"""interop/std_v1/identity.py tests."""

from thief_peer.interop.std_v1.identity import build_identity


def test_build_identity_has_every_spec_required_field():
    identity = build_identity(
        group_id="thief-team",
        group_name="Thief Team",
        members=["alice", "bob"],
        repos={"cop": "https://example.com/cop", "thief": "https://example.com/thief"},
        mcp_servers={"cop": "https://example.com/cop/mcp", "thief": "https://example.com/thief/mcp"},
        llm_model="claude-sonnet-5",
    )
    assert set(identity) == {
        "group_id", "group_name", "git_commit_hash", "github_commit",
        "members", "repos", "mcp_servers", "llm_model", "spec",
    }


def test_build_identity_commit_hash_is_40_hex_chars():
    identity = build_identity(
        group_id="g", group_name="G", members=["a"],
        repos={"cop": "x", "thief": "y"}, mcp_servers={"cop": "x", "thief": "y"},
        llm_model="template",
    )
    assert len(identity["git_commit_hash"]) == 40
    assert identity["git_commit_hash"] == identity["github_commit"]


def test_build_identity_never_mutates_the_caller_supplied_collections():
    members = ["alice"]
    repos = {"cop": "x", "thief": "y"}
    identity = build_identity(
        group_id="g", group_name="G", members=members, repos=repos,
        mcp_servers={"cop": "x", "thief": "y"}, llm_model="template",
    )
    identity["members"].append("mallory")
    identity["repos"]["cop"] = "tampered"
    assert members == ["alice"]
    assert repos == {"cop": "x", "thief": "y"}
