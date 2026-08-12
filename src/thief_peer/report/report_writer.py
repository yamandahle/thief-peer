"""report_writer (PRD_7 §2.7): assembles the four Table-20 JSON artifacts
(PDF / PLAN.md §5 field requirements) and emails them as attachments (rule 34)."""

import json
from pathlib import Path

from thief_peer.exceptions import ProviderError, TransportError
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
    is_counted: bool = True,
) -> dict:
    del league_counter, is_counted  # league bookkeeping stays out of the four JSON files

    game_id = match_result["game_id"]
    game_uid = match_result["game_uid"]
    sub_game_number = match_result["sub_game_number"]
    group_ids = match_result["group_ids"]
    timezone = match_result["timezone"]

    artifacts = {
        "declaration": build_declaration(
            game_id,
            game_uid,
            timezone=timezone,
            game_started_at=match_result["game_started_at"],
            game_ended_at=match_result["game_ended_at"],
            num_sub_games=match_result["num_sub_games"],
            max_tokens_per_game=match_result["max_tokens_per_game"],
            own=match_result["own"],
            opponent=match_result["opponent"],
        ),
        "config": build_config(
            match_result["shared_config_terms"],
            game_id,
            game_uid,
            sub_game_number,
            group_ids,
        ),
        "log": build_log(
            match_result["log_summary"],
            game_id,
            game_uid,
        ),
        "result": build_result(
            game_id,
            game_uid,
            timezone,
            group_ids,
            match_result["sub_games"],
            match_result["final_result_aggregate"],
            match_result["mutual_sha256"],
        ),
    }

    filenames = artifact_filenames(game_id, sub_game_number)
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    for key, artifact in artifacts.items():
        (results_path / filenames[key]).write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    email_attachments = {filenames[key]: artifacts[key] for key in filenames}

    try:
        gatekeeper.execute(
            email_sender.send_report_bundle,
            email_service,
            recipient,
            email_attachments,
            subject=f"Police-Thief match report — {game_uid}",
        )
        artifacts["email_sent"] = True
    except (TransportError, ProviderError) as exc:
        print(f"[Warning] Email send skipped: {exc}")
        artifacts["email_sent"] = False

    return artifacts
