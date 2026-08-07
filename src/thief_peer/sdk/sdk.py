"""ThiefSdk (PRD_2 §2.4): the single entry point business logic sits behind
(SDK mandate) — `cli.py` never touches `infra`/`domain` directly. Stage 2
gives it just `smoke_test()`, a diagnostic method deleted once Stage 3's
real `run()` game loop replaces it.
"""

import threading

from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import build_server, wait_until_ready
from thief_peer.shared.config import ConfigManager


class ThiefSdk:
    def __init__(self, config: ConfigManager):
        self._config = config

    def smoke_test(self) -> dict:
        port = self._config.require("network.my_port")
        opponent_url = self._config.require("network.opponent_url")

        app = build_server(port)
        thread = threading.Thread(
            target=app.run,
            kwargs={
                "transport": "http",
                "host": "0.0.0.0",
                "port": port,
                "show_banner": False,
                "log_level": "warning",
            },
            daemon=True,
        )
        thread.start()
        wait_until_ready(port)

        transport = McpTransport(opponent_url)
        return transport.call("ping", {"payload": {"smoke_test": True}})
