"""FastMCP client (PRD_2 §2.1, §3; extended PRD_5 §2.4, §3): this peer's
outbound half. `McpTransport` bridges FastMCP's async `Client` into the
sync call sites the rest of this codebase uses, and -- since Stage 5 -- adds
real resilience for a non-localhost `opponent_url`: linear backoff retry up
to `max_retries`, the whole attempt (including retries) bounded by
`response_timeout_sec` so a hang can't stall a turn indefinitely.

Retrying is deliberately narrower than "any failure" (`_is_safe_to_retry`,
docs/todoFIXMCP.md task 1): only retry a failure that's provably certain
the request was never transmitted. `receive_commit`/`receive_reveal` on
the far side aren't idempotent -- a retry after the request may have
already reached the peer risks a silent duplicate send and a desynced
round count for the rest of the match. Anything outside that narrow
provably-safe set raises immediately on the first attempt instead.

One persistent `Client`, reused for the whole match, not a fresh one per
call -- found via a real cross-machine match against a real Cop peer: the
old design opened a brand-new `Client` *and* a brand-new asyncio event
loop (`asyncio.run(...)`) on every single `.call()`, and over a real ngrok
tunnel (unlike localhost, where a fresh connection is near-instant and
essentially never fails) that connection churn was frequent enough to fail
mid-match with "Client failed to connect" -- worst of all inside
`receive_capture_claim`'s own synchronous reply, where one flaky
connection attempt failed the *entire* incoming tool call, not just the
reply. `runtime.py` already constructs exactly one `McpTransport` per
match and holds it on `self.transport` for the match's whole duration --
this file is the only place that needed to change.

The `Client`'s own background session task is tied to whichever asyncio
event loop it was started on, so simply holding the same `Client` across
calls isn't enough on its own -- `.call()` is invoked synchronously from
multiple call sites (the main round loop, and `receive_capture_claim`'s
own handler, which FastMCP dispatches to a worker thread). A dedicated
background thread running one persistent event loop for the transport's
whole lifetime, with every `.call()` submitting work to it via
`asyncio.run_coroutine_threadsafe` regardless of which thread it's called
from, is what makes that safe.
"""

import asyncio
import threading
import time

import httpx
from fastmcp import Client

from thief_peer.exceptions import DeadlineExceededError, TransportError


def _is_safe_to_retry(exc: Exception) -> bool:
    """Rule 9 / idempotency: only retry a failure that's provably certain
    the request was never transmitted. `receive_commit`/`receive_reveal`
    on the receiving side (`interop/cop_server_tools.py`) are not
    idempotent -- each unconditionally advances an internal step counter
    -- so retrying anything that might have already reached the peer
    risks a silent duplicate send and a desynced round count for the
    rest of the match (found via a real cross-machine match's connection
    failure investigation, docs/todoFIXMCP.md). Exact signatures below
    confirmed against this repo's own installed fastmcp==3.4.6/httpx, not
    guessed: `httpx.ConnectError`/`ConnectTimeout` and FastMCP's own two
    RuntimeError messages both fire strictly before the request could
    have been transmitted."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        return "Client failed to connect" in message or "Client is not connected" in message
    return False


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
        self._client = Client(opponent_url)
        self._connected = False
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()

    def call(self, tool_name: str, payload: dict) -> dict:
        start = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            remaining = self._response_timeout_sec - (time.monotonic() - start)
            if remaining <= 0:
                raise DeadlineExceededError(
                    f"Call to '{tool_name}' at {self.opponent_url} exceeded "
                    f"the {self._response_timeout_sec}s deadline"
                )
            future = asyncio.run_coroutine_threadsafe(
                self._call_async(tool_name, payload), self._loop
            )
            try:
                return future.result(timeout=remaining)
            except TimeoutError:
                future.cancel()
                raise DeadlineExceededError(
                    f"Call to '{tool_name}' at {self.opponent_url} exceeded "
                    f"the {self._response_timeout_sec}s deadline"
                ) from None
            except Exception as exc:
                last_error = exc
                if not _is_safe_to_retry(exc):
                    raise TransportError(
                        f"Call to '{tool_name}' at {self.opponent_url} failed in a way that "
                        f"may mean the request already reached the peer -- not retrying "
                        f"(receive_commit/receive_reveal aren't idempotent, rule 9): {exc}"
                    ) from exc
                if attempt < self._max_retries:
                    backoff = min(self._retry_backoff_sec * attempt, max(0.0, remaining))
                    time.sleep(backoff)

        raise TransportError(
            f"Could not reach {self.opponent_url} for '{tool_name}' after "
            f"{self._max_retries} attempts: {last_error}"
        )

    async def _call_async(self, tool_name: str, payload: dict) -> dict:
        if not self._connected:
            await self._client.__aenter__()
            self._connected = True
        try:
            result = await self._client.call_tool(tool_name, payload)
            return result.data
        except Exception:
            # A connection-level failure leaves the session unusable --
            # force a clean rebuild so the *next* call (this same retry
            # loop's own next attempt, or a later unrelated one) gets a
            # healthy connection instead of `Client`'s own internals
            # re-raising this same cached failure forever on a still-open
            # session.
            await self._client.close()
            self._connected = False
            raise

    def close(self) -> None:
        """Idempotent teardown -- call once when the match ends
        (`peer/runtime.py::run`)."""
        if self._connected:
            future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
            future.result(timeout=5)
            self._connected = False
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=5)
