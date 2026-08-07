"""peer/round_exchange.py tests (PRD_8 §3). RoundExchange is the mailbox
bridging the MCP server thread (writer, on inbound commit_move/reveal_move)
and the main PeerRuntime loop thread (reader) -- proven here with a real
threading.Thread, not just sequential calls on one thread, since that's the
actual concurrency this class exists to handle."""

import threading
import time

import pytest

from thief_peer.exceptions import DeadlineExceededError
from thief_peer.peer.round_exchange import RoundExchange


def test_wait_for_commit_returns_immediately_once_already_recorded():
    exchange = RoundExchange()
    exchange.record_commit(step=1, h_commit="abc123")

    result = exchange.wait_for_commit(step=1, timeout=1.0)

    assert result == "abc123"


def test_wait_for_reveal_returns_immediately_once_already_recorded():
    exchange = RoundExchange()
    message = {"step": 1, "sender": "cop", "move": "N"}
    exchange.record_reveal(step=1, message=message)

    result = exchange.wait_for_reveal(step=1, timeout=1.0)

    assert result == message


def test_wait_for_commit_unblocks_when_recorded_from_another_thread():
    exchange = RoundExchange()

    def _writer():
        time.sleep(0.05)
        exchange.record_commit(step=1, h_commit="deadbeef")

    threading.Thread(target=_writer, daemon=True).start()

    result = exchange.wait_for_commit(step=1, timeout=2.0)

    assert result == "deadbeef"


def test_wait_for_reveal_unblocks_when_recorded_from_another_thread():
    exchange = RoundExchange()
    message = {"step": 3, "sender": "cop", "move": "S"}

    def _writer():
        time.sleep(0.05)
        exchange.record_reveal(step=3, message=message)

    threading.Thread(target=_writer, daemon=True).start()

    result = exchange.wait_for_reveal(step=3, timeout=2.0)

    assert result == message


def test_wait_for_commit_raises_deadline_exceeded_when_nothing_ever_arrives():
    exchange = RoundExchange(poll_interval=0.01)

    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_commit(step=1, timeout=0.1)


def test_wait_for_reveal_raises_deadline_exceeded_when_nothing_ever_arrives():
    exchange = RoundExchange(poll_interval=0.01)

    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_reveal(step=1, timeout=0.1)


def test_commits_and_reveals_are_tracked_independently_per_step():
    exchange = RoundExchange(poll_interval=0.01)
    exchange.record_commit(step=1, h_commit="hash-for-step-1")

    with pytest.raises(DeadlineExceededError):
        exchange.wait_for_commit(step=2, timeout=0.05)

    assert exchange.wait_for_commit(step=1, timeout=1.0) == "hash-for-step-1"
