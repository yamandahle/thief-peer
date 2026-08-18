"""Report artifact builders (PRD_7 §2.6, §3, §4): pure functions assembling
the four schemas from `PLAN.md` §5 out of data already produced in Stages
1-6. No new game logic here -- only packaging, to avoid the risk of a
report silently recomputing a value differently than how it was sealed.
"""

from datetime import UTC, datetime

from thief_peer.report.artifact_helpers import canonical_sha256
from thief_peer.report.artifact_schemas import SCHEMA_VERSION


def build_declaration(
    game_id: str,
    game_uid: str,
    num_sub_games: int,
    groups: dict,
    timestamp: str | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "game_id": game_id,
        "game_uid": game_uid,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "num_sub_games": num_sub_games,
        "groups": groups,
    }


def build_config(shared_terms: dict, config_name: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "config_name": config_name,
        "terms": shared_terms,
        "config_sha256": canonical_sha256(shared_terms),
    }


def build_log(records: list[dict], audit: dict, protocol: str = "native") -> dict:
    """`protocol` tags which commit-reveal scheme verifies these records --
    default "native" preserves every existing caller's output unchanged.
    gui/replay_view.py reads it back to pick the matching verifier (native's
    domain/crypto.py::CommitReveal vs. std_v1's own interop/std_v1/crypto.py
    scheme -- the two are not interchangeable, see that module's docstring)."""
    return {"schema_version": SCHEMA_VERSION, "records": records, "audit": audit, "protocol": protocol}


def build_result(
    game_id: str,
    game_uid: str,
    groups: list[str],
    num_sub_games: int,
    sub_games: list[dict],
    final_result: dict,
    mutual_agreement: dict,
    timezone: str = "UTC",
    links: dict | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "final_game_result",
        "game_id": game_id,
        "game_uid": game_uid,
        "timezone": timezone,
        "links": links or {},
        "groups": groups,
        "num_sub_games": num_sub_games,
        "sub_games": sub_games,
        "final_result": final_result,
        "mutual_agreement": mutual_agreement,
    }
