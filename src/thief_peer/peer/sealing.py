"""Per-step and Step-0 sealing (PRD_6 §2.1, §2.5, §3): wraps `CommitReveal`
with the specific field shapes the book mandates. `REQUIRED_TERMS` is the
fail-fast guard `PLAN.md` ADR-5 promised -- checked before any socket opens,
not discovered mid-game.
"""

import subprocess

from thief_peer.domain.crypto import CommitReveal
from thief_peer.domain.negotiation import CANONICAL_TERM_KEYS
from thief_peer.shared import sysinfo
from thief_peer.shared.config import ConfigManager
from thief_peer.shared.version import CODE_VERSION

REQUIRED_TERMS = list(CANONICAL_TERM_KEYS.values())


def validate_required_terms(config: ConfigManager) -> None:
    for term in REQUIRED_TERMS:
        config.require(term)


def sealed_step_record(state: str, move: str, intent: str) -> dict:
    payload = {"state": state, "move": move, "intent": intent}
    sealed = CommitReveal.seal(payload)
    return {"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]}


def sealed_spec_record(group_name: str) -> dict:
    """Step-0 declaration (PRD_6 §2.5): hardware spec + code version + the
    exact git commit hash of the code playing this match, sealed together
    so an auditor can reconstruct precisely what competed."""
    payload = {
        "spec": sysinfo.collect_spec(),
        "code_version": CODE_VERSION,
        "github_commit_hash": current_git_commit_hash(),
        "group_name": group_name,
    }
    sealed = CommitReveal.seal(payload)
    return {"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]}


def current_git_commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
    )
    return result.stdout.strip()
