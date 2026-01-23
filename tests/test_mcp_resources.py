"""Tests for MCP resources."""

import json
from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.mcp.resources import (
    _read_config,
    _read_metrics,
    _read_review,
    list_resources,
    read_resource,
)


@pytest.mark.asyncio
async def test_list_resources_returns_all():
    """list_resources returns all 3 resources."""
    resources = await list_resources()
    assert len(resources) == 3
    uris = {str(r.uri) for r in resources}
    assert uris == {
        "config://ai-review.yaml",
        "review://latest",
        "metrics://summary",
    }


@pytest.mark.asyncio
async def test_list_resources_have_descriptions():
    """Each resource has a description."""
    resources = await list_resources()
    for resource in resources:
        assert resource.description
        assert resource.name


@pytest.mark.asyncio
async def test_read_resource_dispatches_config():
    """read_resource routes config:// URIs."""
    with patch(
        "pr_review_agent.mcp.resources._read_config",
        return_value="yaml content",
    ):
        result = await read_resource("config://ai-review.yaml")
        assert result == "yaml content"


@pytest.mark.asyncio
async def test_read_resource_dispatches_review():
    """read_resource routes review:// URIs."""
    with patch(
        "pr_review_agent.mcp.resources._read_review",
        return_value="{}",
    ):
        result = await read_resource("review://latest")
        assert result == "{}"


@pytest.mark.asyncio
async def test_read_resource_dispatches_metrics():
    """read_resource routes metrics:// URIs."""
    with patch(
        "pr_review_agent.mcp.resources._read_metrics",
        return_value="{}",
    ):
        result = await read_resource("metrics://summary")
        assert result == "{}"


@pytest.mark.asyncio
async def test_read_resource_unknown():
    """read_resource returns error for unknown scheme."""
    result = await read_resource("unknown://foo")
    assert "Unknown resource" in result


@pytest.mark.asyncio
async def test_read_config_file_exists(tmp_path):
    """_read_config returns file content when present."""
    config_file = tmp_path / ".ai-review.yaml"
    config_file.write_text("limits:\n  max_lines: 500\n")
    with patch(
        "pr_review_agent.mcp.resources.Path",
        return_value=config_file,
    ):
        result = await _read_config("config://ai-review.yaml")
        assert "max_lines" in result


@pytest.mark.asyncio
async def test_read_config_file_missing(tmp_path):
    """_read_config returns message when file not found."""
    missing = tmp_path / ".ai-review.yaml"
    with patch(
        "pr_review_agent.mcp.resources.Path",
        return_value=missing,
    ):
        result = await _read_config("config://ai-review.yaml")
        assert "No .ai-review.yaml found" in result


@pytest.mark.asyncio
async def test_read_review_no_supabase():
    """_read_review returns error without credentials."""
    with patch.dict("os.environ", {}, clear=True):
        result = await _read_review("review://latest")
        data = json.loads(result)
        assert "SUPABASE_URL" in data["error"]


@pytest.mark.asyncio
async def test_read_review_latest():
    """_read_review fetches latest review."""
    with patch.dict(
        "os.environ",
        {"SUPABASE_URL": "http://test", "SUPABASE_KEY": "key"},
    ):
        mock_result = MagicMock()
        mock_result.data = [{"pr_number": 42, "outcome": "approved"}]
        with patch("supabase.create_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.limit.return_value = mock_table
            mock_table.execute.return_value = mock_result

            result = await _read_review("review://latest")
            data = json.loads(result)
            assert data["pr_number"] == 42


@pytest.mark.asyncio
async def test_read_review_specific_pr():
    """_read_review fetches specific PR review."""
    with patch.dict(
        "os.environ",
        {"SUPABASE_URL": "http://test", "SUPABASE_KEY": "key"},
    ):
        mock_result = MagicMock()
        mock_result.data = [{"pr_number": 5, "outcome": "changes_requested"}]
        with patch("supabase.create_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.limit.return_value = mock_table
            mock_table.execute.return_value = mock_result

            result = await _read_review("review://org/repo/5")
            data = json.loads(result)
            assert data["pr_number"] == 5


@pytest.mark.asyncio
async def test_read_review_invalid_uri():
    """_read_review returns error for bad URI format."""
    with patch.dict(
        "os.environ",
        {"SUPABASE_URL": "http://test", "SUPABASE_KEY": "key"},
    ):
        result = await _read_review("review://bad")
        data = json.loads(result)
        assert "Invalid review URI" in data["error"]


@pytest.mark.asyncio
async def test_read_review_not_found():
    """_read_review returns error when no review exists."""
    with patch.dict(
        "os.environ",
        {"SUPABASE_URL": "http://test", "SUPABASE_KEY": "key"},
    ):
        mock_result = MagicMock()
        mock_result.data = []
        with patch("supabase.create_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.limit.return_value = mock_table
            mock_table.execute.return_value = mock_result

            result = await _read_review("review://latest")
            data = json.loads(result)
            assert "No review found" in data["error"]


@pytest.mark.asyncio
async def test_read_metrics_no_supabase():
    """_read_metrics returns error without credentials."""
    with patch.dict("os.environ", {}, clear=True):
        result = await _read_metrics("metrics://summary")
        data = json.loads(result)
        assert "SUPABASE_URL" in data["error"]


@pytest.mark.asyncio
async def test_read_metrics_summary():
    """_read_metrics returns computed summary."""
    with patch.dict(
        "os.environ",
        {"SUPABASE_URL": "http://test", "SUPABASE_KEY": "key"},
    ):
        mock_result = MagicMock()
        mock_result.data = [
            {
                "cost_usd": 0.05,
                "confidence_score": 0.85,
                "outcome": "approved",
                "llm_called": True,
            },
            {
                "cost_usd": 0.0,
                "confidence_score": None,
                "outcome": "skipped",
                "llm_called": False,
            },
        ]
        with patch("supabase.create_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.execute.return_value = mock_result

            result = await _read_metrics("metrics://summary")
            data = json.loads(result)
            assert data["total_reviews"] == 2
            assert data["llm_calls"] == 1
            assert data["total_cost_usd"] == 0.05
            assert data["gate_skip_rate"] == 0.5


@pytest.mark.asyncio
async def test_read_metrics_repo_specific():
    """_read_metrics filters by repo."""
    with patch.dict(
        "os.environ",
        {"SUPABASE_URL": "http://test", "SUPABASE_KEY": "key"},
    ):
        mock_result = MagicMock()
        mock_result.data = []
        with patch("supabase.create_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.execute.return_value = mock_result

            result = await _read_metrics("metrics://org/repo/summary")
            data = json.loads(result)
            assert data["total_reviews"] == 0


@pytest.mark.asyncio
async def test_read_metrics_invalid_uri():
    """_read_metrics returns error for bad URI format."""
    with patch.dict(
        "os.environ",
        {"SUPABASE_URL": "http://test", "SUPABASE_KEY": "key"},
    ):
        result = await _read_metrics("metrics://bad/path")
        data = json.loads(result)
        assert "Invalid metrics URI" in data["error"]
