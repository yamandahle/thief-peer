"""Each exception must be a distinct, catchable type — never a bare
Exception — so callers can handle config/crypto/simulation/provider
failures differently, per PRD_1 §3."""

import pytest

from thief_peer.exceptions import (
    ConfigError,
    CryptoError,
    DeadlineExceededError,
    ProviderError,
    SimulationError,
    TransportError,
)

ALL_EXCEPTIONS = [
    ConfigError,
    CryptoError,
    SimulationError,
    ProviderError,
    TransportError,
    DeadlineExceededError,
]


@pytest.mark.parametrize("exc_type", ALL_EXCEPTIONS)
def test_each_exception_is_a_distinct_exception_subclass(exc_type):
    assert issubclass(exc_type, Exception)


@pytest.mark.parametrize("exc_type", ALL_EXCEPTIONS)
def test_each_exception_carries_its_message(exc_type):
    with pytest.raises(exc_type, match="boom"):
        raise exc_type("boom")


def test_exceptions_are_siblings_not_related_by_inheritance():
    # A handler catching one specific error type must not accidentally
    # swallow a different failure class.
    assert not issubclass(SimulationError, ConfigError)
    assert not issubclass(ConfigError, SimulationError)
    assert not issubclass(CryptoError, ProviderError)
    assert not issubclass(TransportError, SimulationError)
    assert not issubclass(DeadlineExceededError, TransportError)
    assert not issubclass(TransportError, DeadlineExceededError)
