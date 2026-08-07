"""ThiefSdk (PRD_2 §2.4; PRD_8 §3): the single entry point business logic
sits behind (SDK mandate) -- `cli.py` never touches `infra`/`domain`/`peer`
directly. `smoke_test()` is a diagnostic single-ping round trip; `run()`
builds the real Gatekeeper/Gmail service from config (ADR-4: never call
Gmail directly, only through the Gatekeeper) and drives a full match via
`PeerRuntime`.
"""

from thief_peer.infra import email_sender
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import NullPeerContext, build_server, run_server_in_background
from thief_peer.peer.runtime import PeerRuntime
from thief_peer.shared.config import ConfigManager
from thief_peer.shared.gatekeeper import ApiGatekeeper
from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket


class ThiefSdk:
    def __init__(self, config: ConfigManager):
        self._config = config

    def smoke_test(self) -> dict:
        port = self._config.require("network.my_port")
        opponent_url = self._config.require("network.opponent_url")

        app = build_server(port, NullPeerContext())
        run_server_in_background(app, port)

        transport = McpTransport(opponent_url)
        return transport.call("ping", {"payload": {"smoke_test": True}})

    def run(self, group_name: str) -> dict:
        gatekeeper = ApiGatekeeper(
            token_bucket=TokenBucket(
                capacity=self._config.get("rate_limits.token_bucket_capacity", 5),
                refill_rate=self._config.get("rate_limits.token_bucket_refill_rate", 1.0),
            ),
            dos_detector=DosDetector(
                max_calls=self._config.get("rate_limits.dos_max_calls", 100),
                window_seconds=self._config.get("rate_limits.dos_window_seconds", 60),
            ),
            queue=RequestQueue(max_depth=self._config.get("rate_limits.queue_max_depth", 10)),
        )
        service = email_sender.get_service(self._config.get("email.token_path", "token.json"))
        recipient = self._config.require("email.recipient")

        runtime = PeerRuntime(self._config, group_name, gatekeeper, service, recipient)
        return runtime.run()
