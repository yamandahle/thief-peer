"""Regression test for the `main.py` vs `__main__.py` bug: `python -m
thief_peer` specifically requires a package's `__main__.py` to exist --
`main.py` alone is never auto-invoked by `-m`, and nothing else in this
suite exercises the real `-m` invocation path (test_cli.py always calls
`main()` as a plain function import). Caught only when the user actually
ran the documented command by hand and hit
`No module named thief_peer.__main__`."""

import subprocess
import sys


def test_python_dash_m_thief_peer_is_actually_invocable():
    result = subprocess.run(
        [sys.executable, "-m", "thief_peer", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0
    assert "usage: thief-peer" in result.stdout
