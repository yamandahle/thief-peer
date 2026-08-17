"""Outbound calls to a std_v1 peer, matching the spec's exact tool and
argument names (Section 7): `negotiate(message)`, `receive_turn(message)`,
`submit_audit(payload)`, `receive_control(message)` -- note `submit_audit`
alone takes `payload`, not `message`. Every call wraps this side's own
dict inside that single named argument, matching what the peer's own tool
signature expects to receive as a kwarg -- passing the dict directly
(unwrapped) would send its own keys as individual kwargs instead and fail
immediately against a real peer.

Every call here goes through this repo's own `McpTransport`
(infra/mcp_client.py) unmodified -- one persistent connection for the
whole series, retried only on provably pre-transmission failures. Section
7 notes these four tools are all safe to retry blindly (fire-and-forget
enqueue handlers, no non-idempotent state mutation happens synchronously
inside the call), but nothing here asks the transport to relax its own
narrower, uniform policy -- see this package's own __init__.py docstring.
"""

from __future__ import annotations


def send_negotiate(transport, offer: dict) -> dict:
    return transport.call("negotiate", {"message": offer})


def send_turn(transport, message: dict) -> dict:
    return transport.call("receive_turn", {"message": message})


def send_audit(transport, envelope: dict) -> dict:
    return transport.call("submit_audit", {"payload": envelope})


def send_control(transport, message: dict) -> dict:
    return transport.call("receive_control", {"message": message})
