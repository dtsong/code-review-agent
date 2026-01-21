"""Tests for Supabase metrics logger."""

from unittest.mock import MagicMock, patch

from pr_review_agent.gates.lint_gate import LintGateResult
from pr_review_agent.gates.size_gate import SizeGateResult
from pr_review_agent.github_client import PRData
from pr_review_agent.metrics.supabase_logger import SupabaseLogger
from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import LLMReviewResult, ReviewIssue


def make_pr() -> PRData:
    """Create test PR."""
    return PRData(
        owner="test",
        repo="repo",
        number=1,
        title="Test PR",
        author="testuser",
        description="Test description",
        diff="",
        files_changed=["file.py", "test.py"],
        lines_added=50,
        lines_removed=10,
        base_branch="main",
        head_branch="feature",
        url="https://github.com/test/repo/pull/1",
    )


@patch("pr_review_agent.metrics.supabase_logger.create_client")
def test_log_review_full(mock_create_client):
    """Test logging a full review with all data."""
    mock_table = MagicMock()
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "123"}])
    mock_create_client.return_value = mock_client

    logger = SupabaseLogger("https://test.supabase.co", "test-key")

    pr = make_pr()
    size_result = SizeGateResult(
        passed=True, reason=None, lines_changed=60, files_changed=2, recommendation=None
    )
    lint_result = LintGateResult(passed=True, error_count=0)
    review_result = LLMReviewResult(
        summary="Good PR",
        issues=[
            ReviewIssue(
                severity="minor",
                category="style",
                file="file.py",
                line=10,
                description="Consider rename",
                suggestion="Use better name",
            )
        ],
        strengths=["Clean"],
        input_tokens=100,
        output_tokens=50,
        model="claude-sonnet-4-20250514",
        cost_usd=0.001,
    )
    confidence = ConfidenceResult(score=0.85, level="high", recommendation="auto_approve")

    logger.log_review(
        pr=pr,
        size_result=size_result,
        lint_result=lint_result,
        review_result=review_result,
        confidence=confidence,
        outcome="approved",
        duration_ms=1500,
    )

    mock_client.table.assert_called_with("review_events")
    mock_table.insert.assert_called_once()

    # Verify the data structure
    call_args = mock_table.insert.call_args[0][0]
    assert call_args["repo_owner"] == "test"
    assert call_args["repo_name"] == "repo"
    assert call_args["pr_number"] == 1
    assert call_args["llm_called"] is True
    assert call_args["cost_usd"] == 0.001


@patch("pr_review_agent.metrics.supabase_logger.create_client")
def test_log_review_gated(mock_create_client):
    """Test logging a review that was gated (no LLM call)."""
    mock_table = MagicMock()
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "456"}])
    mock_create_client.return_value = mock_client

    logger = SupabaseLogger("https://test.supabase.co", "test-key")

    pr = make_pr()
    size_result = SizeGateResult(
        passed=False,
        reason="Too large",
        lines_changed=1000,
        files_changed=50,
        recommendation="Split PR",
    )

    logger.log_review(
        pr=pr,
        size_result=size_result,
        lint_result=None,
        review_result=None,
        confidence=None,
        outcome="gated",
        duration_ms=100,
    )

    call_args = mock_table.insert.call_args[0][0]
    assert call_args["size_gate_passed"] is False
    assert call_args["llm_called"] is False
    assert call_args["model_used"] is None
