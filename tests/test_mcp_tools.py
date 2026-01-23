"""Tests for MCP tools."""

from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.mcp.tools import (
    _check_pr_lint,
    _check_pr_size,
    _get_cost_summary,
    _get_review_history,
    _review_pr,
    list_tools,
)


@pytest.mark.asyncio
async def test_list_tools_returns_all():
    """list_tools returns all 5 tools."""
    tools = await list_tools()
    assert len(tools) == 5
    names = {t.name for t in tools}
    assert names == {
        "review_pr",
        "check_pr_size",
        "check_pr_lint",
        "get_review_history",
        "get_cost_summary",
    }


@pytest.mark.asyncio
async def test_list_tools_have_schemas():
    """Each tool has an input schema."""
    tools = await list_tools()
    for tool in tools:
        assert tool.inputSchema is not None
        assert tool.inputSchema["type"] == "object"


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools.get_github_token", return_value="token")
@patch("pr_review_agent.mcp.tools.get_anthropic_key", return_value="key")
async def test_review_pr_size_gate_fails(mock_key, mock_token):
    """review_pr returns early when size gate fails."""
    with (
        patch("pr_review_agent.github_client.GitHubClient") as mock_gh,
        patch("pr_review_agent.config.load_config"),
        patch("pr_review_agent.gates.size_gate.check_size") as mock_size,
    ):
        mock_pr = MagicMock()
        mock_gh.return_value.fetch_pr.return_value = mock_pr
        mock_size.return_value = MagicMock(passed=False, reason="Too large")

        result = await _review_pr({"repo": "org/repo", "pr_number": 1})

        assert len(result) == 1
        assert "Size gate failed" in result[0].text


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools.get_github_token", return_value="token")
@patch("pr_review_agent.mcp.tools.get_anthropic_key", return_value="key")
async def test_review_pr_lint_gate_fails(mock_key, mock_token):
    """review_pr returns early when lint gate fails."""
    with (
        patch("pr_review_agent.github_client.GitHubClient") as mock_gh,
        patch("pr_review_agent.config.load_config"),
        patch("pr_review_agent.gates.size_gate.check_size") as mock_size,
        patch("pr_review_agent.gates.lint_gate.run_lint") as mock_lint,
    ):
        mock_pr = MagicMock()
        mock_gh.return_value.fetch_pr.return_value = mock_pr
        mock_size.return_value = MagicMock(passed=True)
        mock_lint.return_value = MagicMock(passed=False, error_count=5)

        result = await _review_pr({"repo": "org/repo", "pr_number": 1})

        assert "Lint gate failed" in result[0].text


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools.get_github_token", return_value="token")
async def test_check_pr_size_passed(mock_token):
    """check_pr_size returns PASSED status."""
    with (
        patch("pr_review_agent.github_client.GitHubClient") as mock_gh,
        patch("pr_review_agent.config.load_config") as mock_config,
        patch("pr_review_agent.gates.size_gate.check_size") as mock_size,
    ):
        mock_pr = MagicMock(lines_added=50, lines_removed=10, files_changed=["a.py"])
        mock_gh.return_value.fetch_pr.return_value = mock_pr
        mock_size.return_value = MagicMock(passed=True)
        mock_config.return_value = MagicMock(
            limits=MagicMock(max_lines_changed=500, max_files_changed=20)
        )

        result = await _check_pr_size({"repo": "org/repo", "pr_number": 1})

        assert "PASSED" in result[0].text


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools.get_github_token", return_value="token")
async def test_check_pr_lint_failed(mock_token):
    """check_pr_lint returns FAILED with error count."""
    with (
        patch("pr_review_agent.github_client.GitHubClient") as mock_gh,
        patch("pr_review_agent.config.load_config") as mock_config,
        patch("pr_review_agent.gates.lint_gate.run_lint") as mock_lint,
    ):
        mock_pr = MagicMock(files_changed=["a.py"])
        mock_gh.return_value.fetch_pr.return_value = mock_pr
        mock_lint.return_value = MagicMock(passed=False, error_count=12)
        mock_config.return_value = MagicMock(
            linting=MagicMock(fail_threshold=5)
        )

        result = await _check_pr_lint({"repo": "org/repo", "pr_number": 1})

        assert "FAILED" in result[0].text
        assert "12" in result[0].text


@pytest.mark.asyncio
async def test_get_review_history_no_supabase():
    """get_review_history returns error without credentials."""
    with patch.dict("os.environ", {}, clear=True):
        result = await _get_review_history({"repo": "org/repo"})
        assert "SUPABASE_URL" in result[0].text


@pytest.mark.asyncio
async def test_get_cost_summary_no_supabase():
    """get_cost_summary returns error without credentials."""
    with patch.dict("os.environ", {}, clear=True):
        result = await _get_cost_summary({})
        assert "SUPABASE_URL" in result[0].text
