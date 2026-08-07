"""cli.py unit tests. PRD_2 §3 requires cli.py stay a pure
argument-parsing-and-delegation shim (SDK mandate) — these tests confirm
it correctly builds a ConfigManager + ThiefSdk from args and delegates,
without asserting anything about ThiefSdk's internals (that's test_sdk.py's
job)."""

import json

from thief_peer.cli import main


def test_smoke_test_subcommand_delegates_to_sdk_and_prints_result(
    tmp_path, monkeypatch, capsys
):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8802\nopponent_url = "http://127.0.0.1:8802/mcp"\n',
        encoding="utf-8",
    )

    def fake_smoke_test(self):
        return {"pong": True, "received": {"smoke_test": True}}

    monkeypatch.setattr("thief_peer.sdk.sdk.ThiefSdk.smoke_test", fake_smoke_test)

    exit_code = main(["--config", str(toml_path), "smoke-test"])

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"pong": True, "received": {"smoke_test": True}}
