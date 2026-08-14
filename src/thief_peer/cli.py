"""Argument parsing and delegation only (PRD_2 §3, SDK mandate) — this file
must never grow business logic. Stage 2 adds one diagnostic subcommand,
`smoke-test`; later stages add `run` etc. the same way.

`replay` (PRD_10, rule 20 [FATAL]) is dispatched *before* a `ConfigManager`
is ever constructed -- unlike every other subcommand, replaying a saved log
needs no game config at all, and `--config`'s default path isn't guaranteed
to exist for a bare `replay`-only invocation.
"""

import argparse
import json

from thief_peer.sdk.sdk import ThiefSdk, run_replay
from thief_peer.shared.config import ConfigManager
from thief_peer.shared.team_code import validate_team_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thief-peer")
    parser.add_argument("--config", default="config/thief/game.toml")
    parser.add_argument("--shared-config", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("smoke-test")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--group-name", required=True)
    run_parser.add_argument(
        "--team-code",
        default=None,
        help="Rule 45 [MUST]: your unique 8-character Moodle submission "
        "code, no spaces -- separate from --group-name, only needed for "
        "a real counted match, not every dev/warm-up run.",
    )
    run_parser.add_argument("--gui", action="store_true")
    run_parser.add_argument("--warmup", action="store_true")
    auth_parser = subparsers.add_parser("auth-gmail")
    auth_parser.add_argument("--credentials", default="credentials.json")
    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("--log", required=True)
    replay_parser.add_argument("--gui", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "replay":
        return run_replay(args.log, gui=args.gui)

    config = ConfigManager(args.config, args.shared_config)
    sdk = ThiefSdk(config, shared_config_path=args.shared_config)

    if args.command == "smoke-test":
        print(json.dumps(sdk.smoke_test()))
    elif args.command == "run":
        is_counted = not args.warmup
        if args.team_code is not None:
            validate_team_code(args.team_code)
        if args.gui:
            print(
                json.dumps(
                    sdk.run_with_gui(args.group_name, is_counted=is_counted, team_code=args.team_code)
                )
            )
        else:
            print(json.dumps(sdk.run(args.group_name, is_counted=is_counted, team_code=args.team_code)))
    elif args.command == "auth-gmail":
        print(json.dumps({"token_path": sdk.auth_gmail(args.credentials)}))

    return 0
