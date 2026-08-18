"""yanell11's own "settlement hash" convention (their Appendix F Table 17
dialect), distinct from this repo's own Section-11 consensus digest
(`crypto.py::consensus_digest`, `{game_id, game_uid, sub_games}`, compact
separators). Their hash is over `{game_id, aggregate, sub_games}` with
*spaced* separators (the one place their protocol departs from the
otherwise-universal compact form) -- `aggregate` is the series-level
summary (`report.py::final_result`'s own five core fields, with our
extra `tokens_total_series` dropped), and `sub_games` rows are trimmed
to exactly `sub_game_number`, `roles`, `result`, `winner_group`, `score`
(no `tie`/`github_commit`/`tokens`/`audit`/etc.). Report-level only
([REPORT] per our own spec, Section 12's own "nothing else is compared"
note) -- not part of the live wire consensus exchange, but worth
computing identically so the two teams' own reports don't quietly
disagree on a value each claims the other should be able to reproduce.
"""

from __future__ import annotations

import hashlib
import json


def _canonical_spaced(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(", ", ": "))


def build_aggregate(final_result: dict) -> dict:
    """The exact five keys yanell11's own settlement hash expects --
    strips anything this repo's own `final_result` carries beyond that
    (`tokens_total_series`, `games_played_including_this`, etc.)."""
    return {
        "total_score": dict(final_result["total_score"]),
        "sub_games_won": dict(final_result["sub_games_won"]),
        "ties": final_result["ties"],
        "winner_group": final_result["winner_group"],
        "series_tie": final_result["series_tie"],
    }


def build_settlement_rows(consensus_rows: list[dict]) -> list[dict]:
    """Trims Section-11 canonical rows to yanell11's own five settlement
    fields -- `steps`/`github_commit`/`tokens`/`audit`/etc. are
    deliberately outside their preimage."""
    return [
        {
            "sub_game_number": row["sub_game_number"],
            "roles": dict(row["roles"]),
            "result": row["result"],
            "winner_group": row["winner_group"],
            "score": dict(row["score"]),
        }
        for row in consensus_rows
    ]


def settlement_hash(game_id: str, final_result: dict, consensus_rows: list[dict]) -> str:
    obj = {
        "game_id": game_id,
        "aggregate": build_aggregate(final_result),
        "sub_games": build_settlement_rows(consensus_rows),
    }
    return hashlib.sha256(_canonical_spaced(obj).encode("utf-8")).hexdigest()
