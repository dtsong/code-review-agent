"""Tests for MCP server scaffold."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pr_review_agent.mcp.server import (
    get_anthropic_key,
    get_github_token,
    main,
    run_server,
    server,
)


def test_server_name():
    """Server has correct name."""
    assert server.name == "pr-review-agent"


def test_get_github_token_success():
    """Returns token when set."""
    with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
        assert get_github_token() == "ghp_test123"


def test_get_github_token_missing():
    """Raises when GITHUB_TOKEN not set."""
    with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="GITHUB_TOKEN"):
        get_github_token()


def test_get_anthropic_key_success():
    """Returns key when set."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
        assert get_anthropic_key() == "sk-ant-test"


def test_get_anthropic_key_missing():
    """Raises when ANTHROPIC_API_KEY not set."""
    with (
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(ValueError, match="ANTHROPIC_API_KEY"),
    ):
        get_anthropic_key()


def test_server_is_importable():
    """MCP server module can be imported without errors."""
    from pr_review_agent.mcp import server as mod
    assert hasattr(mod, "server")
    assert hasattr(mod, "run_server")
    assert hasattr(mod, "main")


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.server.server")
@patch("pr_review_agent.mcp.server.stdio_server")
async def test_run_server_calls_stdio(mock_stdio, mock_server):
    """run_server uses stdio transport and calls server.run."""
    mock_read = MagicMock()
    mock_write = MagicMock()

    # stdio_server is an async context manager yielding (read, write)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = (mock_read, mock_write)
    mock_stdio.return_value = mock_ctx

    mock_server.run = AsyncMock()
    mock_server.create_initialization_options.return_value = {}

    await run_server()

    mock_server.run.assert_called_once_with(mock_read, mock_write, {})


@patch("asyncio.run")
def test_main_calls_asyncio_run(mock_asyncio_run):
    """main() calls asyncio.run with run_server coroutine."""
    main()
    mock_asyncio_run.assert_called_once()
