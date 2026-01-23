"""Tests for historical context module."""

from unittest.mock import MagicMock, patch

from pr_review_agent.analysis.history import (
    FileHistory,
    HistoricalContext,
    query_file_history,
)


def test_query_file_history_no_supabase():
    """Without Supabase credentials, returns empty context."""
    result = query_file_history(
        files=["src/main.py"],
        repo="owner/repo",
        supabase_url=None,
        supabase_key=None,
    )

    assert result.file_histories == []
    assert result.hot_files == []


@patch("pr_review_agent.analysis.history.create_client")
def test_query_file_history_no_past_reviews(mock_create_client):
    """No past reviews returns empty histories."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[])
    )
    mock_create_client.return_value = mock_client

    result = query_file_history(
        files=["src/main.py"],
        repo="owner/repo",
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
    )

    assert len(result.file_histories) == 1
    assert result.file_histories[0].review_count == 0
    assert result.hot_files == []


@patch("pr_review_agent.analysis.history.create_client")
def test_query_file_history_identifies_hot_files(mock_create_client):
    """Files with many past reviews are flagged as hot."""
    mock_client = MagicMock()
    # Simulate 5 past reviews with issues for this file
    mock_data = [
        {"issues_found": [
            {"file": "src/main.py", "description": "Issue 1"},
            {"file": "src/main.py", "description": "Issue 2"},
        ]},
        {"issues_found": [
            {"file": "src/main.py", "description": "Issue 3"},
        ]},
        {"issues_found": [
            {"file": "src/main.py", "description": "Issue 4"},
        ]},
        {"issues_found": [
            {"file": "src/main.py", "description": "Issue 5"},
            {"file": "src/main.py", "description": "Issue 6"},
        ]},
    ]
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=mock_data)
    )
    mock_create_client.return_value = mock_client

    result = query_file_history(
        files=["src/main.py"],
        repo="owner/repo",
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
    )

    assert result.file_histories[0].is_hot is True
    assert "src/main.py" in result.hot_files
    assert result.file_histories[0].issue_count == 6


@patch("pr_review_agent.analysis.history.create_client")
def test_query_file_history_builds_summary(mock_create_client):
    """Past issues are summarized for LLM context."""
    mock_client = MagicMock()
    mock_data = [
        {"issues_found": [
            {"file": "src/main.py", "description": "Missing null check"},
        ]},
        {"issues_found": [
            {"file": "src/main.py", "description": "Unhandled exception"},
        ]},
        {"issues_found": [
            {"file": "src/main.py", "description": "Race condition"},
        ]},
    ]
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=mock_data)
    )
    mock_create_client.return_value = mock_client

    result = query_file_history(
        files=["src/main.py"],
        repo="owner/repo",
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
    )

    assert "Missing null check" in result.past_issues_summary
    assert "src/main.py" in result.past_issues_summary


@patch("pr_review_agent.analysis.history.create_client")
def test_query_file_history_handles_exceptions(mock_create_client):
    """Exceptions don't crash the review."""
    mock_create_client.side_effect = Exception("Connection failed")

    result = query_file_history(
        files=["src/main.py"],
        repo="owner/repo",
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
    )

    assert isinstance(result, HistoricalContext)
    assert result.file_histories == []


def test_file_history_dataclass():
    """FileHistory can be instantiated with defaults."""
    fh = FileHistory(file_path="src/main.py")

    assert fh.review_count == 0
    assert fh.is_hot is False
    assert fh.common_issues == []
