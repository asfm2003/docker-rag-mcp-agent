"""
Client-side helper that connects to the MCP tool server over SSE.

"http://mcp-server:8100/sse" — again, "mcp-server" is the service name from
docker-compose.yml, resolved via Docker's internal DNS. This is exactly how
you'd call a real hosted MCP server, except here you own and built the box
on the other end of the connection.
"""

import os

from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8100/sse")


async def call_tool(tool_name: str, arguments: dict) -> str:
    async with sse_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            # MCP tool results are a list of content blocks; join any text ones.
            text_parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
            return "\n".join(text_parts) if text_parts else str(result.content)


async def list_tools() -> list[str]:
    async with sse_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return [t.name for t in tools.tools]
