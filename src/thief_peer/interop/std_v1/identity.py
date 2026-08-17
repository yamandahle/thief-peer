"""The negotiation identity block (spec Section 3) -- every field here is
[REPORT]: it flows into result_<game_id>.json (via report/artifact_helpers.py
group_block-equivalent handling for this protocol), so it must be sent in
every per-sub-game handshake, never assumed carried over from an earlier
one.
"""

from __future__ import annotations

from thief_peer.peer.sealing import current_git_commit_hash
from thief_peer.shared import sysinfo


def build_identity(
    group_id: str,
    group_name: str,
    members: list[str],
    repos: dict[str, str],
    mcp_servers: dict[str, str],
    llm_model: str,
) -> dict:
    commit_hash = current_git_commit_hash()
    return {
        "group_id": group_id,
        "group_name": group_name,
        "git_commit_hash": commit_hash,
        "github_commit": commit_hash,
        "members": list(members),
        "repos": dict(repos),
        "mcp_servers": dict(mcp_servers),
        "llm_model": llm_model,
        "spec": sysinfo.collect_spec(),
    }
