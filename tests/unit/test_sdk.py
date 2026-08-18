"""ThiefSdk (PRD_2 §2.4, §3; PRD_8 §3). `smoke_test()` is a diagnostic real
round trip (own server, own opponent_url pointing at itself) kept alive
alongside the real `run()` loop Stage 8 adds. `run()`'s own test only
proves the delegation wiring (config -> Gatekeeper/Gmail service/recipient
-> PeerRuntime.run()) -- PeerRuntime's own behavior has its dedicated tests,
and a real two-process match is the separate integration test (PRD_8 §5)."""

import json

from thief_peer.domain.crypto import CommitReveal
from thief_peer.sdk.sdk import ThiefSdk, run_replay
from thief_peer.shared.config import ConfigManager


def _clean_log(n: int) -> list[dict]:
    records = []
    for i in range(n):
        payload = {"state": f"s{i}", "move": "N", "intent": "truth"}
        sealed = CommitReveal.seal(payload)
        records.append({"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]})
    return records


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

    sdk = ThiefSdk(config, results_dir=tmp_path)
    result = sdk.run("Thief-Team")

    assert result == {"final_result": {"winner_group": "Thief-Team"}}
    assert captured["config"] is config
    assert captured["group_name"] == "Thief-Team"
    assert captured["email_service"] == "fake-service"
    assert captured["recipient"] == "grader@example.com"
    assert captured["gatekeeper"] is not None


def _make_config_with_opponent_recipient(tmp_path, port: int):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\nopponent_recipient = "opponent@theirteam.com"\n',
        encoding="utf-8",
    )
    return ConfigManager(toml_path)


def test_run_counted_reaches_both_the_opponent_and_the_lecturer(tmp_path, monkeypatch):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
    config = _make_config_with_opponent_recipient(tmp_path, port)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["recipient"] = recipient

        def run(self):
            return {"final_result": {"winner_group": "Thief-Team"}}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    sdk = ThiefSdk(config, results_dir=tmp_path)
    sdk.run("Thief-Team", is_counted=True)

    assert captured["recipient"] == "opponent@theirteam.com, grader@example.com"


def test_run_uncounted_reaches_only_the_opponent_never_the_lecturer(tmp_path, monkeypatch):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
    config = _make_config_with_opponent_recipient(tmp_path, port)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["recipient"] = recipient

        def run(self):
            return {"final_result": {"winner_group": "Thief-Team"}}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    sdk = ThiefSdk(config, results_dir=tmp_path)
    sdk.run("Thief-Team", is_counted=False)

    assert captured["recipient"] == "opponent@theirteam.com"


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

    sdk = ThiefSdk(config, results_dir=tmp_path)
    result = sdk.run_with_gui("Thief-Team")

    assert result == {"final_result": {"winner_group": "Thief-Team"}}
    assert captured["group_name"] == "Thief-Team"
    assert captured["started"] is True
    assert isinstance(captured["session_runtime"], _FakeRuntime)
    assert isinstance(captured["session_window"], _FakeWindow)


def test_build_runtime_reads_gatekeeper_numbers_from_the_shared_rate_limiter_gatekeeper_config(
    tmp_path, monkeypatch
):
    """PRD_10 fix: the token bucket / retry / queue-depth numbers must come
    from game.json's shared, negotiated `rate_limiter_gatekeeper` block
    (Appendix F, identical on the Cop side) -- not the private
    `rate_limits.*` key, which never existed in the shared schema and
    silently produced Python's hardcoded fallback defaults instead.
    Reaches into ApiGatekeeper/TokenBucket/RequestQueue's own private
    attributes deliberately, since this is exactly the regression a
    wrong-key-path bug wouldn't otherwise surface in any test."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]

    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    json_path = tmp_path / "game.json"
    json_path.write_text(
        json.dumps(
            {
                "rate_limiter_gatekeeper": {
                    "requests_per_minute": 42,
                    "concurrent_requests": 2,
                    "retry_backoff_sec": 7,
                    "max_retries": 9,
                    "queue_depth": 123,
                }
            }
        ),
        encoding="utf-8",
    )
    config = ConfigManager(toml_path, json_path)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["gatekeeper"] = gatekeeper

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    ThiefSdk(config, results_dir=tmp_path).run("Thief-Team")

    gatekeeper = captured["gatekeeper"]
    assert gatekeeper._max_retries == 9
    assert gatekeeper._backoff_sec == 7
    assert gatekeeper._token_bucket._capacity == 42
    assert gatekeeper._token_bucket._refill_rate == 42 / 60.0
    assert gatekeeper._queue._max_depth == 123


def test_build_runtime_reads_step_deadline_seconds_from_the_private_llm_config(
    tmp_path, monkeypatch
):
    # Book Appendix B: [llm] step_deadline_seconds -- private/local, never
    # negotiated, so it lives in game.toml, not the shared game.json.
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]

    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n'
        "[llm]\nstep_deadline_seconds = 17\n",
        encoding="utf-8",
    )
    json_path = tmp_path / "game.json"
    json_path.write_text("{}", encoding="utf-8")
    config = ConfigManager(toml_path, json_path)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["strategy_deadline_sec"] = kwargs.get("strategy_deadline_sec")

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    ThiefSdk(config, results_dir=tmp_path).run("Thief-Team")

    assert captured["strategy_deadline_sec"] == 17


def test_build_runtime_reads_response_and_watchdog_timeouts_from_the_shared_network_config(
    tmp_path, monkeypatch
):
    # docs/todoFIXMCP.md's config-audit: network_and_league.response_timeout_sec/
    # watchdog_timeout_sec are shared, negotiated values -- previously never
    # read anywhere in src/ at all, so round_deadline_sec/watchdog_timeout_sec
    # always silently used their own hardcoded class defaults instead.
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]

    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    json_path = tmp_path / "game.json"
    json_path.write_text(
        json.dumps({"network_and_league": {"response_timeout_sec": 45, "watchdog_timeout_sec": 90}}),
        encoding="utf-8",
    )
    config = ConfigManager(toml_path, json_path)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["round_deadline_sec"] = kwargs.get("round_deadline_sec")
            captured["watchdog_timeout_sec"] = kwargs.get("watchdog_timeout_sec")

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    ThiefSdk(config, results_dir=tmp_path).run("Thief-Team")

    assert captured["round_deadline_sec"] == 45
    assert captured["watchdog_timeout_sec"] == 90


def test_build_runtime_reads_num_games_and_advances_sub_game_number_each_run(
    tmp_path, monkeypatch
):
    # docs/TodoCloseGaps.md #2: num_sub_games/sub_game_number were never
    # driven by anything -- every run silently defaulted to "1 of 1"
    # regardless of the negotiated network_and_league.num_games.
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]

    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    json_path = tmp_path / "game.json"
    json_path.write_text(json.dumps({"network_and_league": {"num_games": 6}}), encoding="utf-8")
    config = ConfigManager(toml_path, json_path)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = []

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured.append((kwargs.get("sub_game_number"), kwargs.get("num_sub_games")))

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    sdk = ThiefSdk(config, results_dir=tmp_path)
    sdk.run("Thief-Team")
    sdk.run("Thief-Team")
    sdk.run("Thief-Team")

    assert captured == [(1, 6), (2, 6), (3, 6)]


def test_build_runtime_does_not_advance_sub_game_number_for_an_uncounted_run(
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

    captured = []

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured.append(kwargs.get("sub_game_number"))

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    sdk = ThiefSdk(config, results_dir=tmp_path)
    sdk.run("Thief-Team", is_counted=False)
    sdk.run("Thief-Team", is_counted=False)
    sdk.run("Thief-Team", is_counted=True)

    assert captured == [1, 1, 1]


def test_build_runtime_keys_sub_game_number_by_opponent_url_independently(
    tmp_path, monkeypatch
):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port_a = s.getsockname()[1]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port_b = s.getsockname()[1]

    toml_a = tmp_path / "a.toml"
    toml_a.write_text(
        f'[network]\nmy_port = {port_a}\nopponent_url = "http://127.0.0.1:{port_a}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    toml_b = tmp_path / "b.toml"
    toml_b.write_text(
        f'[network]\nmy_port = {port_b}\nopponent_url = "http://127.0.0.1:{port_b}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = []

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured.append(kwargs.get("sub_game_number"))

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    # Both configs share one results_dir (and therefore one counter file),
    # but different opponent_url values -- each series must count from 1.
    ThiefSdk(ConfigManager(toml_a), results_dir=tmp_path).run("Thief-Team")
    ThiefSdk(ConfigManager(toml_b), results_dir=tmp_path).run("Thief-Team")
    ThiefSdk(ConfigManager(toml_a), results_dir=tmp_path).run("Thief-Team")

    assert captured == [1, 1, 2]


def test_build_runtime_falls_back_to_existing_defaults_when_network_and_league_is_absent(
    tmp_path, monkeypatch
):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]

    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    json_path = tmp_path / "game.json"
    json_path.write_text("{}", encoding="utf-8")
    config = ConfigManager(toml_path, json_path)

    monkeypatch.setattr(
        "thief_peer.sdk.sdk.email_sender.get_service", lambda token_path: "fake-service"
    )

    captured = {}

    class _FakeRuntime:
        def __init__(self, cfg, group_name, gatekeeper, email_service, recipient, **kwargs):
            captured["round_deadline_sec"] = kwargs.get("round_deadline_sec")
            captured["watchdog_timeout_sec"] = kwargs.get("watchdog_timeout_sec")

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    ThiefSdk(config, results_dir=tmp_path).run("Thief-Team")

    assert captured["round_deadline_sec"] == 30.0
    assert captured["watchdog_timeout_sec"] == 180.0


def test_smoke_test_reads_response_timeout_sec_from_the_shared_network_config(tmp_path):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]

    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    json_path = tmp_path / "game.json"
    json_path.write_text(
        json.dumps({"network_and_league": {"response_timeout_sec": 12}}), encoding="utf-8"
    )
    config = ConfigManager(toml_path, json_path)
    sdk = ThiefSdk(config)

    result = sdk.smoke_test()

    assert result == {"pong": True, "received": {"smoke_test": True}}


def test_run_passes_is_counted_through_to_peer_runtime(tmp_path, monkeypatch):
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
            captured["is_counted"] = kwargs.get("is_counted")

        def run(self):
            return {}

    monkeypatch.setattr("thief_peer.sdk.sdk.PeerRuntime", _FakeRuntime)

    ThiefSdk(config, results_dir=tmp_path).run("Thief-Team", is_counted=False)

    assert captured["is_counted"] is False


def test_auth_gmail_delegates_to_gmail_auth_with_the_configs_token_path(tmp_path, monkeypatch):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8805\nopponent_url = "http://127.0.0.1:8805/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\ntoken_path = "my-token.json"\n',
        encoding="utf-8",
    )
    config = ConfigManager(toml_path)

    captured = {}

    def fake_ensure_token(credentials_path, token_path):
        captured["credentials_path"] = credentials_path
        captured["token_path"] = token_path
        return tmp_path / token_path

    monkeypatch.setattr("thief_peer.sdk.sdk.gmail_auth.ensure_token", fake_ensure_token)

    sdk = ThiefSdk(config)
    result = sdk.auth_gmail("my-credentials.json")

    assert captured["credentials_path"] == "my-credentials.json"
    assert captured["token_path"] == "my-token.json"
    assert result == str(tmp_path / "my-token.json")


def test_auth_gmail_defaults_credentials_path_and_uses_default_token_path(tmp_path, monkeypatch):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        '[network]\nmy_port = 8806\nopponent_url = "http://127.0.0.1:8806/mcp"\n'
        '[email]\nrecipient = "grader@example.com"\n',
        encoding="utf-8",
    )
    config = ConfigManager(toml_path)

    captured = {}
    monkeypatch.setattr(
        "thief_peer.sdk.sdk.gmail_auth.ensure_token",
        lambda credentials_path, token_path: captured.update(
            credentials_path=credentials_path, token_path=token_path
        )
        or "token.json",
    )

    ThiefSdk(config).auth_gmail()

    assert captured["credentials_path"] == "credentials.json"
    assert captured["token_path"] == "token.json"


def _write_log(tmp_path, records: list[dict]):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps({"schema_version": 1, "records": records, "audit": {}}), encoding="utf-8"
    )
    return log_path


def test_run_replay_prints_verified_ok_and_returns_zero_for_a_clean_log(tmp_path, capsys):
    log_path = _write_log(tmp_path, _clean_log(3))

    exit_code = run_replay(str(log_path))

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Overall: Verified OK" in out
    assert "step 0: Verified OK" in out
    assert "step 1: Verified OK" in out
    assert "step 2: Verified OK" in out


def test_run_replay_prints_tampered_and_returns_one_for_a_corrupted_log(tmp_path, capsys):
    records = _clean_log(3)
    records[1]["payload"]["move"] = "S"  # corrupted after sealing
    log_path = _write_log(tmp_path, records)

    exit_code = run_replay(str(log_path))

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Overall: TAMPERED" in out
    assert "step 0: Verified OK" in out
    assert "step 1: TAMPERED" in out


def test_run_replay_with_gui_opens_a_window_after_the_headless_verdict(
    tmp_path, monkeypatch, capsys
):
    """No real Tkinter involved -- tkinter.Tk/Button and ReplayView are all
    faked at the module attribute level, the same technique
    test_run_with_gui_builds_a_window_and_live_session_and_returns_its_result
    already uses for PeerWindow/LiveSession."""
    log_path = _write_log(tmp_path, _clean_log(2))
    captured = {}

    class _FakeRoot:
        def title(self, text):
            captured["title"] = text

        def mainloop(self):
            captured["mainloop_called"] = True

    class _FakeButton:
        def __init__(self, *args, **kwargs):
            pass

        def pack(self, **kwargs):
            pass

    class _FakeReplayView:
        def __init__(self, root, records, protocol="native"):
            captured["view_records"] = records
            captured["protocol"] = protocol

        def step_back(self):
            pass

        def step_forward(self):
            pass

    monkeypatch.setattr("tkinter.Tk", lambda: _FakeRoot())
    monkeypatch.setattr("tkinter.Button", _FakeButton)
    monkeypatch.setattr("thief_peer.gui.replay_view.ReplayView", _FakeReplayView)

    exit_code = run_replay(str(log_path), gui=True)

    assert exit_code == 0
    assert captured["mainloop_called"] is True
    assert len(captured["view_records"]) == 2
    printed = capsys.readouterr().out
    assert "Overall: Verified OK" in printed  # headless verdict still printed first
