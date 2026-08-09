"""Pre-game negotiation signature (PRD_6 §3; PLAN.md ADR-6). Reuses
CommitReveal unmodified, over a canonical, documented wire vocabulary --
not our internal `game.json` schema -- so interoperability with an
independently-built Cop repo depends only on both sides producing the same
values for these keys, never on matching each other's local field naming.

`scent_lock_hash` (ch.4.5, rule 23 FATAL) rides alongside the sealed terms:
the three `scent_*` wire keys above already lock the raw *numbers* via
Commit-Reveal, but two independently-written ScentField implementations
could still diverge on kernel layout or rounding while reporting identical
numbers -- this catches that class of drift, which the numbers alone can't.
"""

import secrets

from thief_peer.domain.crypto import CommitReveal
from thief_peer.domain.scent_lock import scent_lock_hash
from thief_peer.exceptions import ConfigError
from thief_peer.shared.config import ConfigManager

# Canonical wire key -> our local ConfigManager dotted key. Both peers must
# agree on the wire keys (the left column); each is free to name its own
# local schema however it likes (the right column is purely internal to
# this repo).
CANONICAL_TERM_KEYS: dict[str, str] = {
    "grid_size": "board_and_agents.grid_size",
    "num_agents": "board_and_agents.num_agents",
    "axis_origin_corner": "board_and_agents.axis_origin_corner",
    "axis_start_index": "board_and_agents.axis_start_index",
    "thief_start": "board_and_agents.thief_start",
    "cop_start": "board_and_agents.cop_start",
    "map_area": "world.map_area",
    "hint_word_limit": "world.hint_max_words",
    "move_set": "movement_and_barriers.move_set",
    "max_barriers": "movement_and_barriers.max_barriers",
    "max_moves": "movement_and_barriers.max_moves",
    "survival_threshold": "movement_and_barriers.survival_threshold",
    "capture_reward_cop": "scoring.capture_cop",
    "capture_reward_thief": "scoring.capture_thief",
    "survival_reward_cop": "scoring.survival_cop",
    "survival_reward_thief": "scoring.survival_thief",
    "tie_score": "scoring.tie_score",
    "technical_loss": "scoring.technical_loss",
    "scent_center_intensity": "pheromones.pheromone_center_intensity",
    "scent_decay_rate": "pheromones.pheromone_decay",
    "scent_field_size": "pheromones.pheromone_grid_size",
}


def canonical_terms(config: ConfigManager) -> dict:
    return {wire_key: config.require(local_key) for wire_key, local_key in CANONICAL_TERM_KEYS.items()}


def _scent_lock_hash_of(terms: dict) -> str:
    return scent_lock_hash(
        terms["scent_center_intensity"], terms["scent_decay_rate"], terms["scent_field_size"]
    )


class Negotiation:
    @staticmethod
    def signed(terms: dict) -> dict:
        sealed = CommitReveal.seal(terms)
        return {
            "terms": terms,
            "nonce": sealed["nonce"],
            "commit": sealed["commit"],
            "scent_lock_hash": _scent_lock_hash_of(terms),
        }

    @staticmethod
    def verify_peer(
        their_terms: dict,
        their_nonce: str,
        their_commit: str,
        my_terms: dict,
        their_scent_lock_hash: str,
    ) -> None:
        if not CommitReveal.verify(their_terms, their_nonce, their_commit):
            raise ConfigError(
                "Peer's negotiation commit does not match their revealed terms "
                "-- possible tamper, rejecting before any port opens."
            )
        for key, expected in my_terms.items():
            actual = their_terms.get(key)
            if actual != expected:
                raise ConfigError(
                    f"Negotiated terms mismatch on {key!r}: mine={expected!r} theirs={actual!r}"
                )
        if not secrets.compare_digest(_scent_lock_hash_of(my_terms), their_scent_lock_hash):
            raise ConfigError(
                "Peer's scent-lock hash does not match ours (ch.4.5, rule 23) -- "
                "the pheromone formula implementations have diverged even though "
                "the negotiated numbers match."
            )
