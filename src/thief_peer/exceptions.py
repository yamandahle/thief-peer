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


class DeadlineExceededError(Exception):
    """An MCP call (including any retries) exceeded response_timeout_sec
    (Stage 5) -- distinct from TransportError so the turn FSM can resolve
    this specific case straight to TECHNICAL_LOSS rather than retrying
    something that has already run out of time."""


class RateLimitedError(Exception):
    """A wrapped API call hit an HTTP 429 (Too Many Requests) (Stage 7).
    Callers passed to ApiGatekeeper.execute() raise this specific type on a
    429 so the Gatekeeper can back off deliberately, distinct from other
    transient failures which only get retried once."""
