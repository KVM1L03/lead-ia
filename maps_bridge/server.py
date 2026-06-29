"""maps_bridge MCP server — no tools registered yet."""
import time

from fastmcp import FastMCP

mcp = FastMCP("maps-bridge")

if __name__ == "__main__":
    print("maps_bridge started")
    while True:
        time.sleep(60)
