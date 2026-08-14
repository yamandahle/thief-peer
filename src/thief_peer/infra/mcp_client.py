"""FastMCP client (PRD_2 §2.1, §3; extended PRD_5 §2.4, §3): this peer's
outbound half. `McpTransport` bridges FastMCP's async `Client` into the
sync call sites the rest of this codebase uses, and -- since Stage 5 -- adds
real resilience for a non-localhost `opponent_url`: linear backoff retry up
to `max_retries`, the whole attempt (including retries) bounded by
`response_timeout_sec` so a hang can't stall a turn indefinitely.

`retryable=False` (default `True`) skips the retry loop entirely, one
attempt only. Blind retry is only safe for genuinely idempotent calls
(the scent-map pull). For a commit/reveal-shaped call, if the *response*
is just slow rather than lost, the opponent's server may have already
applied it once -- retrying resends the identical payload, and their own
non-idempotent belief update (`belief.observe_hint`-equivalent on their
side) would fold the same evidence in twice, corrupting their Bayesian
math because of a retry on *our* end. The Cop team hit and fixed the
identical risk on their own side this same way (no retry anywhere in
their commit/reveal path) rather than building receiving-side
deduplication -- matching that choice here, not inventing a different one.
"""

import asyncio
import time

from fastmcp import Client

from thief_peer.exceptions import DeadlineExceededError, TransportError


class McpTransport:
    def __init__(
        self,
        opponent_url: str,
        retry_backoff_sec: float = 5.0,
        max_retries: int = 3,
        response_timeout_sec: float = 30.0,
    ):
        self.opponent_url = opponent_url
        self._retry_backoff_sec = retry_backoff_sec
        self._max_retries = max_retries
        self._response_timeout_sec = response_timeout_sec

    def call(self, tool_name: str, payload: dict, retryable: bool = True) -> dict:
        start = time.monotonic()
        last_error: Exception | None = None
        max_attempts = self._max_retries if retryable else 1

        for attempt in range(1, max_attempts + 1):
            remaining = self._response_timeout_sec - (time.monotonic() - start)
            if remaining <= 0:
                raise DeadlineExceededError(
                    f"Call to '{tool_name}' at {self.opponent_url} exceeded "
                    f"the {self._response_timeout_sec}s deadline"
                )
            try:
                return asyncio.run(
                    asyncio.wait_for(self._call_async(tool_name, payload), timeout=remaining)
                )
            except TimeoutError:
                raise DeadlineExceededError(
                    f"Call to '{tool_name}' at {self.opponent_url} exceeded "
                    f"the {self._response_timeout_sec}s deadline"
                ) from None
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts:
                    backoff = min(self._retry_backoff_sec * attempt, max(0.0, remaining))
                    time.sleep(backoff)

        raise TransportError(
            f"Could not reach {self.opponent_url} for '{tool_name}' after "
            f"{max_attempts} attempts: {last_error}"
        )

    async def _call_async(self, tool_name: str, payload: dict) -> dict:
        async with Client(self.opponent_url) as client:
            result = await client.call_tool(tool_name, payload)
            return result.data
