"""MCP server implementation for PR Review Agent."""

import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("pr-review-agent")


def get_github_token() -> str:
    """Get GitHub token from environment."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable required")
    return token


def get_anthropic_key() -> str:
    """Get Anthropic API key from environment."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY environment variable required")
    return key


async def run_server():
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    """Entry point for pr-review-mcp command."""
    import asyncio

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
