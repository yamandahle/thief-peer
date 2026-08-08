"""ThiefSdk (PRD_2 §2.4, §3; PRD_8 §3). `smoke_test()` is a diagnostic real
round trip (own server, own opponent_url pointing at itself) kept alive
alongside the real `run()` loop Stage 8 adds. `run()`'s own test only
proves the delegation wiring (config -> Gatekeeper/Gmail service/recipient
-> PeerRuntime.run()) -- PeerRuntime's own behavior has its dedicated tests,
and a real two-process match is the separate integration test (PRD_8 §5)."""

from thief_peer.sdk.sdk import ThiefSdk
from thief_peer.shared.config import ConfigManager


def _make_config(tmp_path, port: int):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    return ConfigManager(toml_path)


def test_smoke_test_round_trips_against_itself(tmp_path):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]

    config = _make_config(tmp_path, port)
    sdk = ThiefSdk(config)

    result = sdk.smoke_test()

    assert result == {"pong": True, "received": {"smoke_test": True}}


def test_run_builds_a_gatekeeper_and_email_service_from_config_and_delegates(
    tmp_path, monkeypatch
):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
    config = _make_config(tmp_path, port)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["config"] = cfg
            captured["group_name"] = group_name
            captured["gatekeeper"] = gatekeeper
            captured["email_service"] = email_service
            captured["recipient"] = recipient

        def run(self):
            return {"final_result": {"winner_group": "Thief-Team"}}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    sdk = ThiefSdk(config)
    result = sdk.run("Thief-Team")

    assert result == {"final_result": {"winner_group": "Thief-Team"}}
    assert captured["config"] is config
    assert captured["group_name"] == "Thief-Team"
    assert captured["email_service"] == "fake-service"
    assert captured["recipient"] == "grader@example.com"
    assert captured["gatekeeper"] is not None


def test_run_with_gui_builds_a_window_and_live_session_and_returns_its_result(
    tmp_path, monkeypatch
):
    """No real Tkinter involved -- PeerWindow/LiveSession are lazily
    imported inside run_with_gui, so monkeypatching the real gui modules'
    attributes (not sdk.py's own namespace) is what the local import picks
    up at call time."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
    config = _make_config(tmp_path, port)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["group_name"] = group_name

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    class _FakeWindow:
        pass

    monkeypatch.setattr("thief_peer.gui.window.PeerWindow", _FakeWindow)

    class _FakeSession:
        def __init__(self, runtime, window):
            captured["session_runtime"] = runtime
            captured["session_window"] = window
            self.match_result = {"final_result": {"winner_group": "Thief-Team"}}

        def start(self):
            captured["started"] = True

    monkeypatch.setattr("thief_peer.gui.live_session.LiveSession", _FakeSession)

    sdk = ThiefSdk(config)
    result = sdk.run_with_gui("Thief-Team")

    assert result == {"final_result": {"winner_group": "Thief-Team"}}
    assert captured["group_name"] == "Thief-Team"
    assert captured["started"] is True
    assert isinstance(captured["session_runtime"], _FakeRuntime)
    assert isinstance(captured["session_window"], _FakeWindow)
