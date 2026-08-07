"""Thin launcher (PRD_2 §3) — delegates straight to `cli.main`, no logic."""

from thief_peer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
