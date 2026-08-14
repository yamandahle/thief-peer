"""Real-match parameter comparison harness, run by direct request:
actual games, not a simulation (docs/WEIGHT_TUNING_EXPERIMENT.md and
docs/HEURISTIC_ABLATION.md are both explicitly the simulated kind, and
this project has already been burned once by trusting a simulator's win
rate over real match behavior -- see that file's 2026-08-12 history).

Launches the real yamanagh-cop process and a real thief-peer process on
this machine (cop_v1 protocol, localhost, config/thief/
game_cop_local_test_tuning.toml + scripts/variant_brain.py) for each of
several weight configurations, several real games each, and records the
actual win/loss from each match's own JSON result -- never a simulated
proxy metric.

The Cop side uses her own real RLCopBrain + promoted checkpoint
(config/cop_rl_local_test.toml, this repo -- deliberately kept out of her
working directory so nothing there is ever touched; selects her
already-existing class through her own PRD 13 dotted-path mechanism, the
same idea as this repo's own --thief_class override), not the
deterministic baseline CopBrain -- the first attempt at this comparison
used the baseline and got the identical 10-5 score in all 24 real games,
which wasn't a real signal (see docs/real_match_results.json's own first
run and the conversation that found this).

Dev tooling only. Run manually with
`uv run python scripts/real_match_harness.py`. Saves full results to
docs/real_match_results.json.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

THIEF_ROOT = Path(__file__).resolve().parent.parent
COP_ROOT = THIEF_ROOT.parent / "yamanagh-cop"
SHARED_CONFIG = COP_ROOT / "config" / "shared" / "config_dev_g01.json"
COP_PRIVATE_CONFIG = THIEF_ROOT / "config" / "cop_rl_local_test.toml"
RESULTS_PATH = THIEF_ROOT / "docs" / "real_match_results.json"

GAMES_PER_CONFIG = 6
MAX_ATTEMPTS_PER_CONFIG = GAMES_PER_CONFIG * 3  # bounded retry for transient failures
COP_STARTUP_WAIT_SECONDS = 6.0  # RLCopBrain loads a ~570KB Q-table checkpoint on startup
MATCH_TIMEOUT_SECONDS = 150

# label -> env var overrides for EnvConfiguredThiefBrain. Unset vars fall
# back to the real shipped defaults (expected_distance=1.0, mobility=1.5,
# lookahead=0.1, lookahead_candidates=5, scent=0.5).
CONFIGURATIONS = {
    "shipped_defaults": {},
    "no_mobility_signal": {"THIEF_MOBILITY_WEIGHT": "0.0"},
    "higher_expected_distance": {"THIEF_EXPECTED_DISTANCE_WEIGHT": "2.0"},
    "no_scent_signal": {"THIEF_SCENT_WEIGHT": "0.0"},
}


def _free_the_ports() -> None:
    # best-effort: a prior run's Cop process should already have exited on
    # its own once its match ended, same as every manual run so far did.
    time.sleep(0.5)


def run_one_match(env_overrides: dict, game_index: int) -> dict:
    """Never raises -- a transient failure (connection race, an
    occasional slow RL-inference round pushing a match past
    MATCH_TIMEOUT_SECONDS) must not take down the whole batch and lose
    every result gathered so far. Every failure path returns an "error"
    dict instead, same shape as the JSON-decode failure case already
    handled below, so `main()` has one uniform way to detect and retry
    a bad attempt."""
    cop_proc = subprocess.Popen(
        [
            "uv", "run", "python", "-m", "cop", "peer",
            "--private-config", str(COP_PRIVATE_CONFIG),
            "--shared-config", "config/shared/config_dev_g01.json",
        ],
        cwd=str(COP_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    thief_proc = None
    try:
        time.sleep(COP_STARTUP_WAIT_SECONDS)

        env = dict(os.environ)
        env["PYTHONPATH"] = str(THIEF_ROOT / "scripts")
        env.update(env_overrides)

        thief_proc = subprocess.run(
            [
                "uv", "run", "python", "-m", "thief_peer",
                "--config", "config/thief/game_cop_local_test_tuning.toml",
                "--shared-config", str(SHARED_CONFIG),
                "run", "--group-name", "Thief-Team", "--warmup",
            ],
            cwd=str(THIEF_ROOT),
            capture_output=True,
            text=True,
            env=env,
            timeout=MATCH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.run already killed the timed-out child on this path.
        return {
            "error": f"thief process exceeded {MATCH_TIMEOUT_SECONDS}s and was killed",
            "stdout_tail": (exc.stdout or b"").decode("utf-8", "replace")[-2000:] if isinstance(exc.stdout, bytes) else (exc.stdout or "")[-2000:],
            "stderr_tail": (exc.stderr or b"").decode("utf-8", "replace")[-2000:] if isinstance(exc.stderr, bytes) else (exc.stderr or "")[-2000:],
        }
    finally:
        try:
            cop_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            cop_proc.kill()
            cop_proc.wait(timeout=10)

    stdout_lines = [line for line in thief_proc.stdout.strip().splitlines() if line]
    if not stdout_lines:
        return {
            "error": "no output from thief process",
            "stdout_tail": thief_proc.stdout[-2000:],
            "stderr_tail": thief_proc.stderr[-2000:],
        }
    try:
        result = json.loads(stdout_lines[-1])
    except json.JSONDecodeError:
        return {
            "error": "final line was not valid JSON",
            "stdout_tail": thief_proc.stdout[-2000:],
            "stderr_tail": thief_proc.stderr[-2000:],
        }

    final = result.get("final_result", {})
    return {
        "winner_group": final.get("winner_group"),
        "won": final.get("winner_group") == "Thief-Team",
        "total_score": final.get("total_score"),
        "audit_passed": result.get("audit", {}).get("passed"),
    }


def _save(results: dict, elapsed: float, complete: bool) -> None:
    """Called after every single game, not just at the end -- a crash or
    an interrupted run must never lose results already gathered (found
    the hard way: an earlier run hit an unhandled subprocess.TimeoutExpired
    and lost all 20 games it had already completed, since saving only
    happened once, at the very end)."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "games_per_config": GAMES_PER_CONFIG,
                "configurations": results,
                "elapsed_seconds": elapsed,
                "complete": complete,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> dict:
    started_at = time.monotonic()
    results = {}
    print(f"Real-match parameter comparison -- {GAMES_PER_CONFIG} real games/config\n")

    for label, env_overrides in CONFIGURATIONS.items():
        print(f"=== {label} ({env_overrides or 'shipped defaults'}) ===")
        games = []
        attempts = 0
        valid = 0
        while valid < GAMES_PER_CONFIG and attempts < MAX_ATTEMPTS_PER_CONFIG:
            attempts += 1
            _free_the_ports()
            outcome = run_one_match(env_overrides, attempts)
            games.append(outcome)
            if "error" in outcome:
                print(f"  attempt {attempts}: ERROR -- {outcome['error']} (retrying)")
            else:
                valid += 1
                mark = "WON " if outcome["won"] else "lost"
                print(
                    f"  game {valid}: {mark}  score={outcome['total_score']}  "
                    f"audit_passed={outcome['audit_passed']}"
                )
            results[label] = {
                "env_overrides": env_overrides,
                "games": games,
                "wins": sum(1 for g in games if g.get("won")),
                "win_rate": (
                    sum(1 for g in games if g.get("won")) / valid if valid else None
                ),
            }
            _save(results, time.monotonic() - started_at, complete=False)

        if valid < GAMES_PER_CONFIG:
            print(f"  !! only reached {valid}/{GAMES_PER_CONFIG} valid games after {attempts} attempts")
        wr = results[label]["win_rate"]
        wr_str = f"{wr:.2f}" if wr is not None else "n/a"
        print(f"  -> {results[label]['wins']}/{valid} real wins, win_rate={wr_str}\n")

    elapsed = time.monotonic() - started_at
    _save(results, elapsed, complete=True)
    print(f"({elapsed:.1f}s total) Saved full results to {RESULTS_PATH}")
    return results


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
