"""Thin launcher (PRD_2 §3) — delegates straight to `cli.main`, no logic.

Was misnamed `main.py` since Stage 2: `python -m thief_peer` specifically
requires a package's `__main__.py` to exist, not just any module named
`main` -- `main.py` alone is never auto-invoked by `-m`. Nothing in the
test suite caught this because `test_cli.py` always calls `main()` as a
plain function import, never through a real `python -m thief_peer`
subprocess invocation -- found only when the user actually ran the
documented command by hand.
"""

from thief_peer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
