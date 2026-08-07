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


def build_log(records: list[dict], audit: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "records": records, "audit": audit}


def build_result(final_result: dict, mutual_agreement_signature: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "final_result": final_result,
        "mutual_agreement_signature": mutual_agreement_signature,
    }
