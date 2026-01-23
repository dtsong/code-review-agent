"""Tests for MCP server scaffold."""

from unittest.mock import patch

import pytest

from pr_review_agent.mcp.server import (
    get_anthropic_key,
    get_github_token,
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
