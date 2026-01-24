"""Tests for MCP tools."""

from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.mcp.tools import (
    _check_pr_lint,
    _check_pr_size,
    _get_cost_summary,
    _get_review_history,
    _review_pr,
    call_tool,
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


# --- call_tool dispatcher tests ---


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools._review_pr")
async def test_call_tool_dispatches_review_pr(mock_fn):
    """call_tool routes review_pr to _review_pr."""
    mock_fn.return_value = [MagicMock(text="ok")]
    await call_tool("review_pr", {"repo": "o/r", "pr_number": 1})
    mock_fn.assert_called_once_with({"repo": "o/r", "pr_number": 1})


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools._check_pr_size")
async def test_call_tool_dispatches_check_pr_size(mock_fn):
    """call_tool routes check_pr_size to _check_pr_size."""
    mock_fn.return_value = [MagicMock(text="ok")]
    await call_tool("check_pr_size", {"repo": "o/r", "pr_number": 1})
    mock_fn.assert_called_once_with({"repo": "o/r", "pr_number": 1})


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools._check_pr_lint")
async def test_call_tool_dispatches_check_pr_lint(mock_fn):
    """call_tool routes check_pr_lint to _check_pr_lint."""
    mock_fn.return_value = [MagicMock(text="ok")]
    await call_tool("check_pr_lint", {"repo": "o/r", "pr_number": 1})
    mock_fn.assert_called_once_with({"repo": "o/r", "pr_number": 1})


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools._get_review_history")
async def test_call_tool_dispatches_get_review_history(mock_fn):
    """call_tool routes get_review_history to _get_review_history."""
    mock_fn.return_value = [MagicMock(text="ok")]
    await call_tool("get_review_history", {"repo": "o/r"})
    mock_fn.assert_called_once_with({"repo": "o/r"})


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools._get_cost_summary")
async def test_call_tool_dispatches_get_cost_summary(mock_fn):
    """call_tool routes get_cost_summary to _get_cost_summary."""
    mock_fn.return_value = [MagicMock(text="ok")]
    await call_tool("get_cost_summary", {"days": 7})
    mock_fn.assert_called_once_with({"days": 7})


@pytest.mark.asyncio
async def test_call_tool_unknown_tool():
    """Unknown tool name returns error message."""
    result = await call_tool("nonexistent_tool", {})
    assert "Unknown tool" in result[0].text
    assert "nonexistent_tool" in result[0].text


# --- LLM review path tests ---


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools.get_github_token", return_value="token")
@patch("pr_review_agent.mcp.tools.get_anthropic_key", return_value="key")
async def test_review_pr_full_success(mock_key, mock_token):
    """Full review success returns markdown with issues."""
    with (
        patch("pr_review_agent.github_client.GitHubClient") as mock_gh,
        patch("pr_review_agent.config.load_config") as mock_config,
        patch("pr_review_agent.gates.size_gate.check_size") as mock_size,
        patch("pr_review_agent.gates.lint_gate.run_lint") as mock_lint,
        patch("pr_review_agent.review.llm_reviewer.LLMReviewer") as mock_llm_class,
        patch("pr_review_agent.review.confidence.calculate_confidence") as mock_conf,
    ):
        mock_pr = MagicMock(
            diff="+ code", description="desc",
            files_changed=["a.py"], lines_added=10, lines_removed=5,
        )
        mock_gh.return_value.fetch_pr.return_value = mock_pr
        mock_config.return_value = MagicMock(
            llm=MagicMock(default_model="claude-sonnet-4-20250514")
        )
        mock_size.return_value = MagicMock(passed=True)
        mock_lint.return_value = MagicMock(passed=True)

        mock_issue = MagicMock(
            severity="major", file="a.py", line=5, description="Bug here"
        )
        mock_review = MagicMock(
            summary="Found issues",
            issues=[mock_issue],
            model="claude-sonnet-4-20250514",
            cost_usd=0.002,
        )
        mock_llm_class.return_value.review.return_value = mock_review
        mock_conf.return_value = MagicMock(score=0.7, level="medium")

        result = await _review_pr({"repo": "org/repo", "pr_number": 1})

        assert "Review: org/repo#1" in result[0].text
        assert "Found issues" in result[0].text
        assert "major" in result[0].text.lower()


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools.get_github_token", return_value="token")
@patch("pr_review_agent.mcp.tools.get_anthropic_key", return_value="key")
async def test_review_pr_no_issues(mock_key, mock_token):
    """Review with no issues omits Issues section."""
    with (
        patch("pr_review_agent.github_client.GitHubClient") as mock_gh,
        patch("pr_review_agent.config.load_config") as mock_config,
        patch("pr_review_agent.gates.size_gate.check_size") as mock_size,
        patch("pr_review_agent.gates.lint_gate.run_lint") as mock_lint,
        patch("pr_review_agent.review.llm_reviewer.LLMReviewer") as mock_llm_class,
        patch("pr_review_agent.review.confidence.calculate_confidence") as mock_conf,
    ):
        mock_pr = MagicMock(
            diff="+ code", description="desc",
            files_changed=["a.py"], lines_added=10, lines_removed=5,
        )
        mock_gh.return_value.fetch_pr.return_value = mock_pr
        mock_config.return_value = MagicMock(
            llm=MagicMock(default_model="claude-sonnet-4-20250514")
        )
        mock_size.return_value = MagicMock(passed=True)
        mock_lint.return_value = MagicMock(passed=True)
        mock_review = MagicMock(
            summary="All good", issues=[], model="claude-sonnet-4-20250514", cost_usd=0.001
        )
        mock_llm_class.return_value.review.return_value = mock_review
        mock_conf.return_value = MagicMock(score=0.9, level="high")

        result = await _review_pr({"repo": "org/repo", "pr_number": 1})

        assert "All good" in result[0].text
        assert "Issues" not in result[0].text


# --- check_pr_size failed with reason ---


@pytest.mark.asyncio
@patch("pr_review_agent.mcp.tools.get_github_token", return_value="token")
async def test_check_pr_size_failed_with_reason(mock_token):
    """check_pr_size includes reason text when failed."""
    with (
        patch("pr_review_agent.github_client.GitHubClient") as mock_gh,
        patch("pr_review_agent.config.load_config") as mock_config,
        patch("pr_review_agent.gates.size_gate.check_size") as mock_size,
    ):
        mock_pr = MagicMock(lines_added=600, lines_removed=100, files_changed=["a.py"] * 25)
        mock_gh.return_value.fetch_pr.return_value = mock_pr
        mock_size.return_value = MagicMock(passed=False, reason="Exceeds 500 line limit")
        mock_config.return_value = MagicMock(
            limits=MagicMock(max_lines_changed=500, max_files_changed=20)
        )

        result = await _check_pr_size({"repo": "org/repo", "pr_number": 1})

        assert "FAILED" in result[0].text
        assert "Exceeds 500 line limit" in result[0].text


# --- Supabase query tests ---


@pytest.mark.asyncio
async def test_get_review_history_with_results():
    """Returns formatted list of past reviews."""
    mock_result = MagicMock()
    mock_result.data = [
        {"pr_number": 10, "outcome": "approved", "confidence_score": 0.9, "cost_usd": 0.002},
        {
            "pr_number": 8, "outcome": "changes_requested",
            "confidence_score": 0.5, "cost_usd": 0.003,
        },
    ]

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.execute.return_value = mock_result

    mock_client = MagicMock()
    mock_client.table.return_value = mock_query

    with (
        patch.dict("os.environ", {"SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "key"}),
        patch("supabase.create_client", return_value=mock_client),
    ):
        result = await _get_review_history({"repo": "org/repo"})

        assert "Review History" in result[0].text
        assert "PR#10" in result[0].text
        assert "approved" in result[0].text


@pytest.mark.asyncio
async def test_get_review_history_empty():
    """Returns no-reviews message when empty."""
    mock_result = MagicMock()
    mock_result.data = []

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.execute.return_value = mock_result

    mock_client = MagicMock()
    mock_client.table.return_value = mock_query

    with (
        patch.dict("os.environ", {"SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "key"}),
        patch("supabase.create_client", return_value=mock_client),
    ):
        result = await _get_review_history({"repo": "org/repo"})

        assert "No reviews found" in result[0].text


@pytest.mark.asyncio
async def test_get_cost_summary_with_data():
    """Calculates totals from review data."""
    mock_result = MagicMock()
    mock_result.data = [
        {"cost_usd": 0.01, "model_used": "claude-sonnet", "repo_owner": "o", "repo_name": "r"},
        {"cost_usd": 0.02, "model_used": "claude-sonnet", "repo_owner": "o", "repo_name": "r"},
    ]

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.execute.return_value = mock_result

    mock_client = MagicMock()
    mock_client.table.return_value = mock_query

    with (
        patch.dict("os.environ", {"SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "key"}),
        patch("supabase.create_client", return_value=mock_client),
    ):
        result = await _get_cost_summary({"days": 7})

        assert "Cost Summary" in result[0].text
        assert "$0.03" in result[0].text
        assert "Reviews: 2" in result[0].text


@pytest.mark.asyncio
async def test_get_cost_summary_empty():
    """Zero reviews returns $0."""
    mock_result = MagicMock()
    mock_result.data = []

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.execute.return_value = mock_result

    mock_client = MagicMock()
    mock_client.table.return_value = mock_query

    with (
        patch.dict("os.environ", {"SUPABASE_URL": "http://localhost", "SUPABASE_KEY": "key"}),
        patch("supabase.create_client", return_value=mock_client),
    ):
        result = await _get_cost_summary({})

        assert "$0.00" in result[0].text
        assert "Reviews: 0" in result[0].text
