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

    def fake_run(self, group_name, is_counted=True):
        captured["group_name"] = group_name
        captured["is_counted"] = is_counted
        return {"final_result": {"winner_group": "Thief-Team"}}

    monkeypatch.setattr("thief_peer.sdk.sdk.ThiefSdk.run", fake_run)

    exit_code = main(["--config", str(toml_path), "run", "--group-name", "Thief-Team"])

    assert exit_code == 0
    assert captured["group_name"] == "Thief-Team"
    assert captured["is_counted"] is True
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"final_result": {"winner_group": "Thief-Team"}}


def test_run_subcommand_with_warmup_flag_marks_the_match_uncounted(
    tmp_path, monkeypatch, capsys
):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8808\nopponent_url = "http://127.0.0.1:8808/mcp"\n',
        encoding="utf-8",
    )

    captured = {}

    def fake_run(self, group_name, is_counted=True):
        captured["is_counted"] = is_counted
        return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.ThiefSdk.run", fake_run)

    exit_code = main(["--config", str(toml_path), "run", "--group-name", "Thief-Team", "--warmup"])

    assert exit_code == 0
    assert captured["is_counted"] is False


def test_run_subcommand_with_gui_flag_delegates_to_run_with_gui(
    tmp_path, monkeypatch, capsys
):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8804\nopponent_url = "http://127.0.0.1:8804/mcp"\n',
        encoding="utf-8",
    )

    captured = {}

    def fake_run(self, group_name, is_counted=True):
        captured["headless_called"] = True
        return {}

    def fake_run_with_gui(self, group_name, is_counted=True):
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


def test_replay_subcommand_delegates_to_run_replay_without_needing_a_config(
    tmp_path, monkeypatch
):
    """The whole point: no game.toml exists anywhere near tmp_path, and
    --config was never passed, yet replay must still work -- it needs no
    game config at all (cli.py dispatches it before ConfigManager is ever
    constructed)."""
    captured = {}

    def fake_run_replay(log_path, gui=False):
        captured["log_path"] = log_path
        captured["gui"] = gui
        return 0

    monkeypatch.setattr("thief_peer.cli.run_replay", fake_run_replay)
    monkeypatch.chdir(tmp_path)  # confirms the default --config path is never touched

    exit_code = main(["replay", "--log", "results/log_x.json"])

    assert exit_code == 0
    assert captured["log_path"] == "results/log_x.json"
    assert captured["gui"] is False


def test_replay_subcommand_with_gui_flag_passes_it_through(tmp_path, monkeypatch):
    captured = {}

    def fake_run_replay(log_path, gui=False):
        captured["gui"] = gui
        return 1

    monkeypatch.setattr("thief_peer.cli.run_replay", fake_run_replay)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["replay", "--log", "results/log_x.json", "--gui"])

    assert exit_code == 1
    assert captured["gui"] is True


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
