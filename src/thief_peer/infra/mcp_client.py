"""FastMCP client (PRD_2 §2.1, §3): this peer's outbound half. Calls tools
exposed by the opponent's server. `McpTransport` bridges FastMCP's async
`Client` into the sync call sites the rest of this codebase uses.
"""

import asyncio

from fastmcp import Client

from thief_peer.exceptions import TransportError


class McpTransport:
    def __init__(self, opponent_url: str):
        self.opponent_url = opponent_url

    def call(self, tool_name: str, payload: dict) -> dict:
        try:
            return asyncio.run(self._call_async(tool_name, payload))
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError(
                f"Call to '{tool_name}' at {self.opponent_url} failed: {exc}"
            ) from exc

    async def _call_async(self, tool_name: str, payload: dict) -> dict:
        async with Client(self.opponent_url) as client:
            result = await client.call_tool(tool_name, payload)
            return result.data
