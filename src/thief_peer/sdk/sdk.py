"""ThiefSdk (PRD_2 §2.4; PRD_8 §3): the single entry point business logic
sits behind (SDK mandate) -- `cli.py` never touches `infra`/`domain`/`peer`
directly. `smoke_test()` is a diagnostic single-ping round trip; `run()`
builds the real Gatekeeper/Gmail service from config (ADR-4: never call
Gmail directly, only through the Gatekeeper) and drives a full match via
`PeerRuntime`; `run_with_gui()` does the same but wires the match to a live
`PeerWindow` instead of running headless (a gap left over from PRD_7/PRD_8:
the GUI and `PeerRuntime.view()` both existed but nothing connected them).
`gui.*` is imported lazily inside `run_with_gui()` only, so `run()`/
`smoke_test()` never require Tkinter to be usable. `auth_gmail()` is the
one-time OAuth2 bootstrap (Appendix א §1.5) that produces the token file
`run()`/`run_with_gui()` assume already exists -- a separate, explicit step
a human runs once, never invoked automatically mid-match. `is_counted`
(rule 52 fix) defaults to `True` (a real league match); pass `False` for a
warm-up/test run so `report_writer`'s per-opponent league counter never
gets silently inflated.

`run_replay` (PRD_10, closing rule 20 [FATAL]) is a module-level function,
not a `ThiefSdk` method: replaying a saved log needs no game config at all,
so it deliberately doesn't require constructing a `ConfigManager`/`ThiefSdk`
first -- `cli.py` calls it directly, before any config is loaded, exactly
like every other `sdk.py` function stays the one place `cli.py` is allowed
to reach into `gui`/`domain`.
"""

import json
from pathlib import Path

from thief_peer.infra import email_sender, gmail_auth
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import NullPeerContext, build_server, run_server_in_background
from thief_peer.peer.runtime import PeerRuntime
from thief_peer.shared.config import ConfigManager
from thief_peer.shared.gatekeeper import ApiGatekeeper
from thief_peer.shared.rate_limiter import DosDetector, RequestQueue, TokenBucket


class ThiefSdk:
    def __init__(self, config: ConfigManager, shared_config_path: str | None = None):
        self._config = config
        self._shared_config_path = shared_config_path

    def smoke_test(self) -> dict:
        port = self._config.require("network.my_port")
        opponent_url = self._config.require("network.opponent_url")

        app = build_server(port, NullPeerContext())
        run_server_in_background(app, port)

        transport = McpTransport(opponent_url)
        return transport.call("ping", {"payload": {"smoke_test": True}})

    def run(self, group_name: str, is_counted: bool = True, team_code: str | None = None) -> dict:
        return self._build_runtime(group_name, is_counted, team_code).run()

    def run_with_gui(
        self, group_name: str, is_counted: bool = True, team_code: str | None = None
    ) -> dict:
        from thief_peer.gui.live_session import LiveSession
        from thief_peer.gui.window import PeerWindow

        runtime = self._build_runtime(group_name, is_counted, team_code)
        session = LiveSession(runtime, PeerWindow())
        session.start()
        return session.match_result

    def auth_gmail(self, credentials_path: str = "credentials.json") -> str:
        token_path = self._config.get("email.token_path", "token.json")
        return str(gmail_auth.ensure_token(credentials_path, token_path))

    def _build_runtime(
        self, group_name: str, is_counted: bool = True, team_code: str | None = None
    ) -> PeerRuntime:
        # rate_limiter_gatekeeper.* (PRD_10 fix): this block was added to the
        # *shared*, negotiated game.json in Stage 9 specifically to match the
        # book's Appendix-F numbers (identical on the Cop side) -- but this
        # method was never updated off its Stage-7-era private-tuning design,
        # so it silently read from "rate_limits.*" (a key that only ever
        # existed in game.toml's own [rate_limits] section, never in the
        # shared config) and got Python's hardcoded fallback defaults every
        # time instead. requests_per_minute/max_retries/retry_backoff_sec/
        # queue_depth are all part of that negotiated contract now, so they
        # come from here, not a private override. DOS-detector thresholds
        # have no equivalent field in the shared schema at all (each side's
        # own unilateral defense choice, not something to negotiate) -- those
        # two alone still legitimately come from game.toml's [rate_limits].
        requests_per_minute = self._config.get("rate_limiter_gatekeeper.requests_per_minute", 30)
        gatekeeper = ApiGatekeeper(
            token_bucket=TokenBucket(
                capacity=requests_per_minute,
                refill_rate=requests_per_minute / 60.0,
            ),
            dos_detector=DosDetector(
                max_calls=self._config.get("rate_limits.dos_max_calls", 100),
                window_seconds=self._config.get("rate_limits.dos_window_seconds", 60),
            ),
            queue=RequestQueue(
                max_depth=self._config.get("rate_limiter_gatekeeper.queue_depth", 100)
            ),
            max_retries=self._config.get("rate_limiter_gatekeeper.max_retries", 3),
            backoff_sec=self._config.get("rate_limiter_gatekeeper.retry_backoff_sec", 5.0),
        )
        service = email_sender.get_service(self._config.get("email.token_path", "token.json"))
        recipient = self._config.require("email.recipient")
        return PeerRuntime(
            self._config,
            group_name,
            gatekeeper,
            service,
            recipient,
            is_counted=is_counted,
            shared_config_path=self._shared_config_path,
            team_code=team_code,
        )


def run_replay(log_path: str, gui: bool = False) -> int:
    """Rule 20 [FATAL]: re-verifies a saved match log's Commit-Reveal chain
    and prints a per-step + overall verdict. `log_path` is one of
    `report/report_writer.py`'s own persisted artifacts (`results/
    log_<game_uid>.json`, built by `report/artifacts.py::build_log`) --
    `data["records"]` is already the exact `{"payload": {...,"nonce":...},
    "commit":...}` shape `gui/replay_view.py::verify_step`/`replay` expect,
    so no separate log format exists to convert between. Headless-first
    (the verdict never depends on Tkinter being importable, matching the
    Cop repo's own `cli_replay.py`); `--gui` opens a step-navigable window
    afterward, never the only way to get an answer. Returns a process exit
    code (`0` = Verified OK, `1` = TAMPERED) -- rule 20's own "no appeal"
    framing means an ambiguous exit code here would defeat the tool's
    purpose."""
    from thief_peer.gui.replay_view import replay, verify_step

    data = json.loads(Path(log_path).read_text(encoding="utf-8"))
    records = data["records"]

    overall = replay(records)
    print(f"Overall: {overall}")
    for index, entry in enumerate(records):
        print(f"  step {index}: {verify_step(entry)}")

    if gui:
        import tkinter as tk

        from thief_peer.gui.replay_view import ReplayView

        root = tk.Tk()
        root.title("Thief Peer -- Replay Viewer")
        view = ReplayView(root, records)
        tk.Button(root, text="< Back", command=view.step_back).pack(side="left")
        tk.Button(root, text="Forward >", command=view.step_forward).pack(side="right")
        root.mainloop()

    return 0 if overall == "Verified OK" else 1
