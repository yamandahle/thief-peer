"""ConfigManager v0 — private-only TOML loader with a dotted-key `.get()`
API (PRD_1 §3). The shared, signed `game.json` overlay is deliberately
deferred to Stage 4 (PRD_2 §2.3, PRD_4) — this stage's peer never needs
game content, only its own local settings, per `PLAN.md` ADR-5's config split.
"""

import tomllib
from pathlib import Path
from typing import Any

from thief_peer.exceptions import ConfigError


class ConfigManager:
    def __init__(self, toml_path: str | Path):
        self._path = Path(toml_path)
        self._data = self._load(self._path)

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except FileNotFoundError as exc:
            raise ConfigError(f"Missing config file: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted_key: str) -> Any:
        """Like `get`, but fails fast (PRD_2 §2.3) instead of silently
        returning a default — for keys a networked command cannot run
        without, e.g. `network.my_port`."""
        missing = object()
        value = self.get(dotted_key, missing)
        if value is missing:
            raise ConfigError(
                f"Required config key '{dotted_key}' missing from {self._path}"
            )
        return value
