"""SubGameCounter (docs/TodoCloseGaps.md #2): tracks "which sub-game
number comes next" for a given opponent connection, persisted across
separate `cli.py run` invocations the same way `LeagueCounter` tracks
per-opponent games-played. Deliberately mirrors `LeagueCounter`'s own
file structure/shape (same persisted-JSON, same peek-vs-record split) --
a second, independent counter file rather than repurposing
`league_counter.json`, since "which sub-game am I about to play" and
"how many games total have I played against this opponent" are
genuinely different questions with different lifetimes.

Keyed by `opponent_url` (from the private `network.opponent_url` config,
known before any handshake) rather than the negotiated `game_id`
(`domain/game_ids.py::derive_game_id`) -- `sub_game_number` has to be
decided and sent as part of the very first outbound Step-0 declaration,
before the opponent's own group name (and therefore `game_id`, which
needs both names) is known at all.
"""

import json
from pathlib import Path


class SubGameCounter:
    def __init__(self, path: str | Path = "results/sub_game_counter.json"):
        self._path = Path(path)

    def next_sub_game_number(self, opponent_key: str, *, is_counted: bool = True) -> int:
        """Returns the next sub-game number for this opponent connection.
        Only persists the advance when `is_counted` is True -- an
        uncounted warm-up run peeks at what the next real sub-game number
        would be without consuming that slot, matching `LeagueCounter`'s
        own `games_played_against` (peek) vs `record_game` (advance)
        split in `report/report_writer.py`."""
        data = self._load()
        candidate = data.get(opponent_key, 0) + 1
        if is_counted:
            data[opponent_key] = candidate
            self._save(data)
        return candidate

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data), encoding="utf-8")
