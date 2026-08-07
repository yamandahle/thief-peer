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
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("smoke-test")

    args = parser.parse_args(argv)

    config = ConfigManager(args.config)
    sdk = ThiefSdk(config)

    if args.command == "smoke-test":
        print(json.dumps(sdk.smoke_test()))

    return 0
