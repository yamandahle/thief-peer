"""ConfigManager — private TOML loader with an optional shared `game.json`
overlay, merged into one dotted-key namespace (`PLAN.md` ADR-5). Deferred
since Stage 1 until a stage actually needed shared game-content terms;
Stage 6's negotiation is that stage. On a key collision the JSON value
wins — it's signed and shared, the private TOML must never be able to
quietly "weaken" a term both sides agreed to.
"""

import json
import tomllib
from pathlib import Path
from typing import Any

from thief_peer.exceptions import ConfigError


class ConfigManager:
    def __init__(self, toml_path: str | Path, json_path: str | Path | None = None):
        self._path = Path(toml_path)
        data = self._load_toml(self._path)
        if json_path is not None:
            json_data = self._load_json(Path(json_path))
            data = _deep_merge(data, json_data)
        self._data = data

    @staticmethod
    def _load_toml(path: Path) -> dict:
        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except FileNotFoundError as exc:
            raise ConfigError(f"Missing config file: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc

    @staticmethod
    def _load_json(path: Path) -> dict:
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError as exc:
            raise ConfigError(f"Missing config file: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

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


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
