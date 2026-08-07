"""Distinct exception types per failure class — never a bare Exception —
so callers can handle config, crypto, simulation, and provider failures
differently. Sibling types, no shared hierarchy beyond Exception itself.
"""


class ConfigError(Exception):
    """A required config term is missing or invalid."""


class CryptoError(Exception):
    """A Commit-Reveal seal/verify operation failed (Stage 6)."""


class SimulationError(Exception):
    """An internal game-rule invariant was violated (e.g. illegal move)."""


class ProviderError(Exception):
    """An LLM/external provider call failed (Stage 4)."""


class TransportError(Exception):
    """A network/MCP transport operation failed: port already in use,
    opponent unreachable, or connection dropped (Stage 2+)."""
