"""ThiefBrain variant for the real-match parameter comparison harness
(scripts/real_match_harness.py), by direct request -- not a simulated
sweep (see docs/WEIGHT_TUNING_EXPERIMENT.md for why simulated win rates
alone were rejected as trustworthy for this project once already).

Reads weight overrides from environment variables at construction time,
so a real `thief_peer run` process can use a different weight set per
invocation via `[strategy] thief_class` (PLAN.md ADR-7's existing
pluggable-strategy mechanism) without ever touching fleeing_brain.py's
shipped constants. Any variable left unset falls back to the real shipped
default -- an unconfigured run of this class behaves identically to the
real `ThiefBrain()`.
"""

import os

from thief_peer.strategy.fleeing_brain import (
    EXPECTED_DISTANCE_WEIGHT,
    LOOKAHEAD_CANDIDATE_COUNT,
    LOOKAHEAD_WEIGHT,
    MOBILITY_WEIGHT,
    SCENT_WEIGHT,
    ThiefBrain,
)


class EnvConfiguredThiefBrain(ThiefBrain):
    def __init__(self):
        super().__init__(
            expected_distance_weight=float(
                os.environ.get("THIEF_EXPECTED_DISTANCE_WEIGHT", EXPECTED_DISTANCE_WEIGHT)
            ),
            mobility_weight=float(os.environ.get("THIEF_MOBILITY_WEIGHT", MOBILITY_WEIGHT)),
            lookahead_weight=float(os.environ.get("THIEF_LOOKAHEAD_WEIGHT", LOOKAHEAD_WEIGHT)),
            lookahead_candidate_count=int(
                os.environ.get("THIEF_LOOKAHEAD_CANDIDATE_COUNT", LOOKAHEAD_CANDIDATE_COUNT)
            ),
            scent_weight=float(os.environ.get("THIEF_SCENT_WEIGHT", SCENT_WEIGHT)),
        )
