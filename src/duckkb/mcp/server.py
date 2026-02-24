from fastmcp import FastMCP
from duckkb.config import settings

# Initialize FastMCP server
mcp = FastMCP("DuckKB")

@mcp.tool()
async def check_health() -> str:
    """Check if the server is running."""
    return "DuckKB is running!"
