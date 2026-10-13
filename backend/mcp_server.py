"""Standalone command-line entrypoint for launching the Mentor AI MCP Server.

Usage:
    # Run over standard I/O (for Claude Desktop, Cursor, Antigravity):
    python backend/mcp_server.py

    # Or with python -m:
    python -m app.services.mcp.server
"""

import asyncio
import os
import sys

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.mcp.server import mcp_server  # noqa: E402


def main() -> None:
    """Run the MCP server over stdio transport."""
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "stdio":
        asyncio.run(mcp_server.run_stdio_async())
    elif transport == "sse":
        port = int(os.getenv("MCP_PORT", "8001"))
        host = os.getenv("MCP_HOST", "0.0.0.0")
        asyncio.run(mcp_server.run_sse_async(host=host, port=port))
    else:
        print(f"Unknown MCP transport: {transport}. Supported: stdio, sse", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
