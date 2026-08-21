"""report_writer (PRD_7 §2.7, §3): assembles the four artifacts, writes
them to disk, and sends the result via the Gatekeeper -- triggered after
every legal match, unconditionally. `LeagueCounter` persists the
per-opponent games-played count across separate match invocations (PRD_7
§2.7) -- lying about this count is an explicit disqualification-level
offense if caught, so it must survive a process restart, not just live in
memory. `is_counted` (rule 52 fix, found in a compliance re-audit) gates
whether *this specific* match actually increments that counter -- uncounted
warm-up/test games are explicitly permitted by the book, but must never
silently inflate the persisted count a real league match's declaration
relies on being accurate (rules 37/38).
"""

import json
from pathlib import Path

from thief_peer.exceptions import ProviderError, TransportError
from thief_peer.infra import email_sender
from thief_peer.report.artifact_helpers import artifact_filenames
from thief_peer.report.artifacts import build_config, build_declaration, build_log
from thief_peer.report.series_result import merge_sub_game_into_series


class LeagueCounter:
    def __init__(self, path: str | Path = "results/league_counter.json"):
        self._path = Path(path)

    def games_played_against(self, opponent_group_id: str) -> int:
        return self._load().get(opponent_group_id, 0)

    def total_games_played(self) -> int:
        """The book's own "Game-Count Declaration" (Sec. 9.2.1, printed
        p.70): "each group declares to its opponent how many games it has
        already played *so far*" -- unqualified, not "against this
        opponent". Confirmed against the book's own worked example: two
        teams' reports for the identical match showed *different* values
        for this field, which is only possible for a league-wide running
        total, never for a per-opponent count (two teams meeting each
        other would necessarily report the same number). Rule 52's own
        one-counted-game-per-opponent enforcement stays exactly on
        `games_played_against`/`record_game` above, unaffected -- this is
        a second, separate view over the same underlying per-opponent
        storage, for the declaration field only."""
        return sum(self._load().values())

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
    counter = league_counter or LeagueCounter()
    if is_counted:
        games_played = counter.record_game(match_result["opponent_group_id"])
    else:
        games_played = counter.games_played_against(match_result["opponent_group_id"])

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
        "result": merge_sub_game_into_series(
            results_dir,
            match_result["game_id"],
            match_result["groups"]["group_1"]["identity"],
            match_result["opponent_group_id"],
            match_result["num_sub_games"],
            match_result["sub_game_entry"],
            games_played,
            match_result.get("league_params", {}),
        ),
    }

    filenames = artifact_filenames(match_result["game_id"], match_result["sub_game_number"])
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    for key, artifact in artifacts.items():
        (results_path / filenames[key]).write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    artifacts["email_sent"] = send_report_email(gatekeeper, email_service, recipient, artifacts["result"])

    return artifacts


def send_report_email(gatekeeper, email_service, recipient: str, report: dict) -> bool:
    """The rule-32 email step, factored out so any protocol's own
    finalization path (native's `write_and_send` above, std_v1's
    `interop/std_v1_opponent.py::send_std_v1_report_email`) sends the exact
    same way rather than duplicating this try/except. Returns whether the
    send actually succeeded -- never raises, since a failed send must never
    take down a match that already finished and has its artifacts safely on
    disk."""
    try:
        gatekeeper.execute(email_sender.send_report, email_service, recipient, report)
        return True
    except (TransportError, ProviderError) as exc:
        # The only two exception types that ever escape ApiGatekeeper.execute
        # (shared/gatekeeper.py's DOS-lock/queue-full checks raise
        # TransportError directly; _call_with_retry wraps every other
        # failure, including a real rate-limit block, as ProviderError after
        # retries are exhausted) -- narrowed from a bare `except Exception`
        # so a genuine bug elsewhere in this call chain still surfaces
        # instead of being silently absorbed here. The caller's own
        # artifacts are already on disk regardless (rules 33/34); this only
        # degrades the rule-32 email step to best-effort, and says so via
        # the return value rather than only printing once and moving on.
        print(f"[Warning] Email send skipped: {exc}")
        return False
