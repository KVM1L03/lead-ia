"""website_bridge MCP server — exposes the fetch_website_facts tool.

Runs as a persistent streamable-http server so the in-memory per-domain cache
survives across tool calls (not a stdio spawn per invocation).
"""

from fastmcp import FastMCP

from shared.schemas import WebsiteFacts
from website_bridge.config import settings
from website_bridge.provider_factory import get_provider

mcp = FastMCP("website-bridge")


@mcp.tool()
async def fetch_website_facts(url: str) -> WebsiteFacts:
    provider = get_provider()
    return await provider.fetch_website_facts(url)


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=settings.WEBSITE_BRIDGE_PORT,
        show_banner=False,
    )
