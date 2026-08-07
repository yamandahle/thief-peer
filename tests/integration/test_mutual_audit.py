"""Stage 6 integration test (TODO_6): proves the "Done" milestone over a
real MCP round trip -- a full per-step commit chain, submitted to a live
opponent server, which cross-verifies it (opponent-verifies-me, never
self-verification, PRD_6 §2.3) and reports PASS on a clean log / FAIL with
the exact tampered step on a corrupted one.
"""

import socket
import threading

import pytest

from thief_peer.domain.crypto import CommitReveal
from thief_peer.infra.mcp_client import McpTransport
from thief_peer.infra.mcp_server import NullPeerContext, build_server, wait_until_ready


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


@pytest.fixture
def opponent_server():
    port = _free_port()
    app = build_server(port, NullPeerContext())
    thread = threading.Thread(
        target=app.run,
        kwargs={
            "transport": "http",
            "host": "127.0.0.1",
            "port": port,
            "show_banner": False,
            "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    wait_until_ready(port)
    yield port


def _sealed_step_chain(n: int) -> list[dict]:
    records = []
    for step in range(n):
        payload = {"state": f"state-{step}", "move": "N", "intent": "truth"}
        sealed = CommitReveal.seal(payload)
        records.append({"payload": {**payload, "nonce": sealed["nonce"]}, "commit": sealed["commit"]})
    return records


def test_a_clean_commit_chain_is_submitted_and_passes_a_real_opponents_audit(opponent_server):
    transport = McpTransport(f"http://127.0.0.1:{opponent_server}/mcp")
    records = _sealed_step_chain(5)

    result = transport.call(
        "submit_audit", {"payload": {"sender": "thief", "result_claim": "survival", "records": records}}
    )

    assert result == {"passed": True, "verified_steps": 5, "failed_steps": []}


def test_a_tampered_commit_chain_is_caught_by_the_real_opponents_audit(opponent_server):
    transport = McpTransport(f"http://127.0.0.1:{opponent_server}/mcp")
    records = _sealed_step_chain(5)
    # Retroactively switch step 3's move -- exactly the temptation
    # Commit-Reveal exists to make provably detectable (PRD_6 §1).
    records[3]["payload"]["move"] = "S"

    result = transport.call(
        "submit_audit", {"payload": {"sender": "thief", "result_claim": "survival", "records": records}}
    )

    assert result["passed"] is False
    assert result["failed_steps"] == [3]
    assert result["verified_steps"] == 5
