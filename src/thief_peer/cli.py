"""Argument parsing and delegation only (PRD_2 §3, SDK mandate) — this file
must never grow business logic. Stage 2 adds one diagnostic subcommand,
`smoke-test`; later stages add `run` etc. the same way.
"""

import argparse
import json

from thief_peer.sdk.sdk import ThiefSdk
from thief_peer.shared.config import ConfigManager


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thief-peer")
    parser.add_argument("--config", default="config/thief/game.toml")
    parser.add_argument("--shared-config", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("smoke-test")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--group-name", required=True)
    run_parser.add_argument("--gui", action="store_true")
    run_parser.add_argument("--warmup", action="store_true")
    auth_parser = subparsers.add_parser("auth-gmail")
    auth_parser.add_argument("--credentials", default="credentials.json")

    args = parser.parse_args(argv)

    config = ConfigManager(args.config, args.shared_config)
    sdk = ThiefSdk(config)

    if args.command == "smoke-test":
        print(json.dumps(sdk.smoke_test()))
    elif args.command == "run":
        is_counted = not args.warmup
        if args.gui:
            print(json.dumps(sdk.run_with_gui(args.group_name, is_counted=is_counted)))
        else:
            print(json.dumps(sdk.run(args.group_name, is_counted=is_counted)))
    elif args.command == "auth-gmail":
        print(json.dumps({"token_path": sdk.auth_gmail(args.credentials)}))

    return 0
