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


def test_run_subcommand_delegates_to_sdk_with_the_group_name_and_prints_result(
    tmp_path, monkeypatch, capsys
):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8803\nopponent_url = "http://127.0.0.1:8803/mcp"\n',
        encoding="utf-8",
    )

    captured = {}

    def fake_run(self, group_name):
        captured["group_name"] = group_name
        return {"final_result": {"winner_group": "Thief-Team"}}

    monkeypatch.setattr("thief_peer.sdk.sdk.ThiefSdk.run", fake_run)

    exit_code = main(["--config", str(toml_path), "run", "--group-name", "Thief-Team"])

    assert exit_code == 0
    assert captured["group_name"] == "Thief-Team"
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"final_result": {"winner_group": "Thief-Team"}}


def test_run_subcommand_with_gui_flag_delegates_to_run_with_gui(
    tmp_path, monkeypatch, capsys
):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8804\nopponent_url = "http://127.0.0.1:8804/mcp"\n',
        encoding="utf-8",
    )

    captured = {}

    def fake_run(self, group_name):
        captured["headless_called"] = True
        return {}

    def fake_run_with_gui(self, group_name):
        captured["group_name"] = group_name
        return {"final_result": {"winner_group": "Thief-Team"}}

    monkeypatch.setattr("thief_peer.sdk.sdk.ThiefSdk.run", fake_run)
    monkeypatch.setattr("thief_peer.sdk.sdk.ThiefSdk.run_with_gui", fake_run_with_gui)

    exit_code = main(["--config", str(toml_path), "run", "--group-name", "Thief-Team", "--gui"])

    assert exit_code == 0
    assert "headless_called" not in captured
    assert captured["group_name"] == "Thief-Team"
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"final_result": {"winner_group": "Thief-Team"}}


def test_auth_gmail_subcommand_delegates_to_sdk_and_prints_the_token_path(
    tmp_path, monkeypatch, capsys
):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8807\nopponent_url = "http://127.0.0.1:8807/mcp"\n',
        encoding="utf-8",
    )

    captured = {}

    def fake_auth_gmail(self, credentials_path):
        captured["credentials_path"] = credentials_path
        return "token.json"

    monkeypatch.setattr("thief_peer.sdk.sdk.ThiefSdk.auth_gmail", fake_auth_gmail)

    exit_code = main(["--config", str(toml_path), "auth-gmail", "--credentials", "creds.json"])

    assert exit_code == 0
    assert captured["credentials_path"] == "creds.json"
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"token_path": "token.json"}
