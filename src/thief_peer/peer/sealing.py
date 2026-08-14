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


def sealed_step_record(
    state: str, move: str, intent: str, hint_text: str, step: int, role: str
) -> dict:
    """The book's Ch.5.3.1 equation is `SHA256(State‖Move‖Intent‖Nonce)` --
    the 4 fields this repo hashed exclusively until now. `hint_text`/`step`/
    `role` extend that (the Cop repo's own elaboration, citing the book's
    reference-implementation record, p.51) -- adopted here as this team's
    own intra-pair standard so a real mutual audit against that specific,
    already-coordinated partner can run for real instead of reporting "not
    evaluated" (see `interop/cop_wire.py`). All three are already known
    locally at commit time (the hint text this turn, the step counter, and
    this peer's fixed role) -- no new wire round-trip is introduced by
    hashing them."""
    payload = {
        "state": state,
        "move": move,
        "intent": intent,
        "hint_text": hint_text,
        "step": step,
        "role": role,
    }
    sealed = CommitReveal.seal(payload)
    return {"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]}


def sealed_spec_record(group_name: str, games_played_so_far: int = 0) -> dict:
    """Step-0 declaration (PRD_6 §2.5): hardware spec + code version + the
    exact git commit hash of the code playing this match, sealed together
    so an auditor can reconstruct precisely what competed. `games_played_so_far`
    (rules 37/38, book p.70) is this side's own counted-game total *before*
    this game -- declared to the opponent at Step-0, not just reported to
    the lecturer afterward; defaults to 0 so an uncoordinated caller (e.g.
    a direct unit test) still gets a valid record."""
    payload = {
        "spec": sysinfo.collect_spec(),
        "code_version": CODE_VERSION,
        "github_commit_hash": current_git_commit_hash(),
        "group_name": group_name,
        "games_played_so_far": games_played_so_far,
    }
    sealed = CommitReveal.seal(payload)
    return {"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]}


def current_git_commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
    )
    return result.stdout.strip()
