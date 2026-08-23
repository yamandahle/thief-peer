"""The negotiation identity block (spec Section 3) -- every field here is
[REPORT]: it flows into result_<game_id>.json (report.py::group_details),
so it must be sent in every per-sub-game handshake, never assumed carried
over from an earlier one.
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
    scent_model_lock: dict | None = None,
    counted_games_played: int | None = None,
) -> dict:
    """`scent_model_lock` and `counted_games_played` are both strictly
    additive, never-required keys -- omitted entirely when not given, per
    Section 9's "optional fields MAY be omitted" posture, and invisible to
    the Section-12 report either way since `report.py::group_details` only
    ever whitelists specific fields off this dict. `counted_games_played`
    (rule-38, reconciled live against yanell11: they'd recorded `null` for
    us with nothing populating it) should be the caller's own already-
    computed `games_played_against_opponent` -- the count *before* this
    series, not `games_played_including_this`, which only makes sense once
    a counted match has actually run."""
    commit_hash = current_git_commit_hash()
    spec = dict(sysinfo.collect_spec())
    if spec.get("gpu") is None:
        # najamjad, live: their declaration validator requires a string for
        # gpu_model and rejected our genuinely-absent-GPU `null` outright,
        # blocking *their* declaration artifact for the whole series (not
        # ours -- report.py's own group_details never required this).
        # sysinfo.collect_spec() itself stays untouched (cop_wire.py's own
        # `gpu_present = spec["gpu"] is not None` still needs the real
        # None) -- this is a std_v1 wire-format concession, not a change to
        # what "no GPU" means internally.
        spec["gpu"] = "none"
    identity = {
        "group_id": group_id,
        "group_name": group_name,
        "git_commit_hash": commit_hash,
        "github_commit": commit_hash,
        "members": list(members),
        "repos": dict(repos),
        "mcp_servers": dict(mcp_servers),
        "llm_model": llm_model,
        "spec": spec,
    }
    if scent_model_lock is not None:
        identity["scent_model_lock"] = scent_model_lock
    if counted_games_played is not None:
        identity["counted_games_played"] = counted_games_played
    return identity
