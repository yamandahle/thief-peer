"""ThiefSdk skeleton (PRD_2 §2.4, §3): Stage 2 only exercises smoke_test(),
a diagnostic method slated for deletion once Stage 3 introduces the real
run() loop. It's tested here as a real round trip (own server, own
opponent_url pointing at itself) since there is no separate Cop process
to test against yet."""

from thief_peer.sdk.sdk import ThiefSdk
from thief_peer.shared.config import ConfigManager


def _make_config(tmp_path, port: int):
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        f'[network]\nmy_port = {port}\nopponent_url = "http://127.0.0.1:{port}/mcp"\n',
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
