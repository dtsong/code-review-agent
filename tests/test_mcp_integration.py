"""Integration tests for MCP server with tools and resources."""

from unittest.mock import MagicMock, patch

import pytest
from mcp.types import TextContent


class TestMCPToolRegistration:
    """Test that tools are properly registered with the server."""

    def test_server_has_list_tools_method(self):
        """Server has list_tools method available."""
        # Import to trigger registration
        from pr_review_agent.mcp import tools  # noqa: F401
        from pr_review_agent.mcp.server import server

        # The server should have list_tools method
        assert hasattr(server, "list_tools")
        assert callable(server.list_tools)

    def test_server_has_call_tool_method(self):
        """Server has call_tool method available."""
        from pr_review_agent.mcp import tools  # noqa: F401
        from pr_review_agent.mcp.server import server

        assert hasattr(server, "call_tool")
        assert callable(server.call_tool)

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self):
        """list_tools returns all expected tools."""
        from pr_review_agent.mcp.tools import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]

        assert "review_pr" in tool_names
        assert "check_pr_size" in tool_names
        assert "check_pr_lint" in tool_names
        assert "get_review_history" in tool_names
        assert "get_cost_summary" in tool_names
        assert len(tools) == 5


class TestMCPResourceRegistration:
    """Test that resources are properly registered with the server."""

    def test_server_has_list_resources_method(self):
        """Server has list_resources method available."""
        from pr_review_agent.mcp import resources  # noqa: F401
        from pr_review_agent.mcp.server import server

        assert hasattr(server, "list_resources")
        assert callable(server.list_resources)

    def test_server_has_read_resource_method(self):
        """Server has read_resource method available."""
        from pr_review_agent.mcp import resources  # noqa: F401
        from pr_review_agent.mcp.server import server

        assert hasattr(server, "read_resource")
        assert callable(server.read_resource)

    @pytest.mark.asyncio
    async def test_list_resources_returns_all_resources(self):
        """list_resources returns all expected resources."""
        from pr_review_agent.mcp.resources import list_resources

        resources = await list_resources()
        uris = [str(r.uri) for r in resources]

        assert "config://ai-review.yaml" in uris
        assert "review://latest" in uris
        assert "metrics://summary" in uris
        assert len(resources) == 3


class TestMCPToolCallIntegration:
    """Integration tests for tool calls through the server."""

    @pytest.mark.asyncio
    async def test_call_unknown_tool_returns_error(self):
        """Calling unknown tool returns error message."""
        from pr_review_agent.mcp.tools import call_tool

        result = await call_tool("nonexistent_tool", {})

        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Unknown tool" in result[0].text

    @pytest.mark.asyncio
    @patch("pr_review_agent.mcp.tools.get_github_token")
    @patch("pr_review_agent.github_client.GitHubClient")
    async def test_check_pr_size_integration(self, mock_gh_class, mock_token):
        """check_pr_size tool works end-to-end."""
        from pr_review_agent.mcp.tools import call_tool

        mock_token.return_value = "fake-token"

        mock_pr = MagicMock()
        mock_pr.lines_added = 50
        mock_pr.lines_removed = 30
        mock_pr.files_changed = ["file1.py", "file2.py"]

        mock_client = MagicMock()
        mock_client.fetch_pr.return_value = mock_pr
        mock_gh_class.return_value = mock_client

        result = await call_tool("check_pr_size", {
            "repo": "owner/repo",
            "pr_number": 123,
        })

        assert len(result) == 1
        assert "Size gate" in result[0].text
        assert "PASSED" in result[0].text

    @pytest.mark.asyncio
    @patch("pr_review_agent.gates.lint_gate.run_lint")
    @patch("pr_review_agent.mcp.tools.get_github_token")
    @patch("pr_review_agent.github_client.GitHubClient")
    async def test_check_pr_lint_integration(self, mock_gh_class, mock_token, mock_lint):
        """check_pr_lint tool works end-to-end."""
        from pr_review_agent.mcp.tools import call_tool

        mock_token.return_value = "fake-token"

        mock_pr = MagicMock()
        mock_pr.files_changed = ["file.py"]

        mock_client = MagicMock()
        mock_client.fetch_pr.return_value = mock_pr
        mock_gh_class.return_value = mock_client

        mock_lint.return_value = MagicMock(passed=True, error_count=0)

        result = await call_tool("check_pr_lint", {
            "repo": "owner/repo",
            "pr_number": 123,
        })

        assert len(result) == 1
        assert "Lint gate" in result[0].text
        assert "PASSED" in result[0].text

    @pytest.mark.asyncio
    async def test_get_review_history_no_supabase(self):
        """get_review_history returns error without Supabase credentials."""
        from pr_review_agent.mcp.tools import call_tool

        with patch.dict("os.environ", {}, clear=True):
            result = await call_tool("get_review_history", {"repo": "owner/repo"})

        assert len(result) == 1
        assert "SUPABASE" in result[0].text

    @pytest.mark.asyncio
    async def test_get_cost_summary_no_supabase(self):
        """get_cost_summary returns error without Supabase credentials."""
        from pr_review_agent.mcp.tools import call_tool

        with patch.dict("os.environ", {}, clear=True):
            result = await call_tool("get_cost_summary", {})

        assert len(result) == 1
        assert "SUPABASE" in result[0].text


class TestMCPResourceReadIntegration:
    """Integration tests for resource reads through the server."""

    @pytest.mark.asyncio
    async def test_read_unknown_resource_returns_error(self):
        """Reading unknown resource returns error message."""
        from pr_review_agent.mcp.resources import read_resource

        result = await read_resource("unknown://something")

        assert "Unknown resource" in result

    @pytest.mark.asyncio
    async def test_read_config_resource(self):
        """Reading config resource returns config file content."""
        from pr_review_agent.mcp.resources import read_resource

        # Config file exists in repo root
        result = await read_resource("config://ai-review.yaml")

        # Should return actual config content or "not found" message
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_read_review_no_supabase(self):
        """Reading review resource returns error without Supabase."""
        import json

        from pr_review_agent.mcp.resources import read_resource

        with patch.dict("os.environ", {}, clear=True):
            result = await read_resource("review://latest")

        data = json.loads(result)
        assert "error" in data
        assert "SUPABASE" in data["error"]

    @pytest.mark.asyncio
    async def test_read_metrics_no_supabase(self):
        """Reading metrics resource returns error without Supabase."""
        import json

        from pr_review_agent.mcp.resources import read_resource

        with patch.dict("os.environ", {}, clear=True):
            result = await read_resource("metrics://summary")

        data = json.loads(result)
        assert "error" in data
        assert "SUPABASE" in data["error"]


class TestMCPEndToEnd:
    """End-to-end tests simulating real MCP interactions."""

    @pytest.mark.asyncio
    @patch("pr_review_agent.review.llm_reviewer.LLMReviewer")
    @patch("pr_review_agent.github_client.GitHubClient")
    @patch("pr_review_agent.mcp.tools.get_anthropic_key")
    @patch("pr_review_agent.mcp.tools.get_github_token")
    async def test_full_review_pipeline(
        self, mock_token, mock_anthropic, mock_gh_class, mock_reviewer_class
    ):
        """Full review_pr tool works with all components."""
        from pr_review_agent.mcp.tools import call_tool

        mock_token.return_value = "fake-token"
        mock_anthropic.return_value = "fake-key"

        # Mock PR data
        mock_pr = MagicMock()
        mock_pr.lines_added = 50
        mock_pr.lines_removed = 30
        mock_pr.files_changed = ["file.py"]
        mock_pr.diff = "+ new code"
        mock_pr.description = "Test PR"

        mock_client = MagicMock()
        mock_client.fetch_pr.return_value = mock_pr
        mock_gh_class.return_value = mock_client

        # Mock LLM review
        mock_review = MagicMock()
        mock_review.summary = "LGTM"
        mock_review.issues = []
        mock_review.model = "claude-sonnet-4-20250514"
        mock_review.cost_usd = 0.001

        mock_reviewer = MagicMock()
        mock_reviewer.review.return_value = mock_review
        mock_reviewer_class.return_value = mock_reviewer

        result = await call_tool("review_pr", {
            "repo": "owner/repo",
            "pr_number": 123,
        })

        assert len(result) == 1
        assert "Review" in result[0].text
        assert "Confidence" in result[0].text
        assert "LGTM" in result[0].text
