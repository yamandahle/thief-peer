"""report_writer (PRD_7 §2.7, §3): assembles the four artifacts, writes
them to disk, and sends the result via the Gatekeeper -- triggered after
every legal match, unconditionally. `LeagueCounter` persists the
per-opponent games-played count across separate match invocations (PRD_7
§2.7) -- lying about this count is an explicit disqualification-level
offense if caught, so it must survive a process restart, not just live in
memory.
"""

import json
from pathlib import Path

from thief_peer.infra import email_sender
from thief_peer.report.artifact_helpers import artifact_filenames
from thief_peer.report.artifacts import build_config, build_declaration, build_log, build_result


class LeagueCounter:
    def __init__(self, path: str | Path = "results/league_counter.json"):
        self._path = Path(path)

    def games_played_against(self, opponent_group_id: str) -> int:
        return self._load().get(opponent_group_id, 0)

    def record_game(self, opponent_group_id: str) -> int:
        data = self._load()
        data[opponent_group_id] = data.get(opponent_group_id, 0) + 1
        self._save(data)
        return data[opponent_group_id]

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data), encoding="utf-8")


def write_and_send(
    match_result: dict,
    gatekeeper,
    email_service,
    recipient: str,
    results_dir: str | Path = "results",
    league_counter: LeagueCounter | None = None,
) -> dict:
    counter = league_counter or LeagueCounter()
    games_played = counter.record_game(match_result["opponent_group_id"])

    declaration = build_declaration(
        game_id=match_result["game_id"],
        game_uid=match_result["game_uid"],
        num_sub_games=match_result["num_sub_games"],
        groups=match_result["groups"],
    )
    declaration["games_played_against_opponent"] = games_played

    artifacts = {
        "declaration": declaration,
        "config": build_config(match_result["shared_terms"], match_result["config_name"]),
        "log": build_log(match_result["records"], match_result["audit"]),
        "result": build_result(
            match_result["final_result"], match_result.get("mutual_agreement_signature")
        ),
    }

    filenames = artifact_filenames(match_result["game_id"], match_result["sub_game_number"])
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    for key, artifact in artifacts.items():
        (results_path / filenames[key]).write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    gatekeeper.execute(email_sender.send_report, email_service, recipient, artifacts["result"])

    return artifacts
