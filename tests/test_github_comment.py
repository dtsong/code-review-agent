"""Tests for GitHub comment formatting."""

from pr_review_agent.output.github_comment import format_as_markdown
from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import LLMReviewResult, ReviewIssue


def test_format_as_markdown_basic():
    """Test basic markdown formatting."""
    review = LLMReviewResult(
        summary="Overall good PR with minor issues",
        issues=[
            ReviewIssue(
                severity="minor",
                category="style",
                file="src/main.py",
                line=42,
                description="Consider using a more descriptive name",
                suggestion="Rename to `process_user_data`",
            )
        ],
        strengths=["Clean code structure", "Good test coverage"],
        concerns=[],
        questions=["Why was this approach chosen over X?"],
        input_tokens=500,
        output_tokens=200,
        model="claude-sonnet-4-20250514",
        cost_usd=0.0045,
    )
    confidence = ConfidenceResult(
        score=0.85,
        level="high",
        recommendation="auto_approve",
    )

    markdown = format_as_markdown(review, confidence)

    assert "## AI Code Review" in markdown
    assert "Overall good PR" in markdown
    assert "minor" in markdown.lower()
    assert "src/main.py" in markdown
    assert "0.85" in markdown
    assert "claude-sonnet" in markdown


def test_format_as_markdown_no_issues():
    """Test formatting when no issues found."""
    review = LLMReviewResult(
        summary="LGTM - clean PR",
        issues=[],
        strengths=["Well tested"],
        model="claude-haiku-4-20250514",
        cost_usd=0.001,
    )
    confidence = ConfidenceResult(
        score=0.95,
        level="high",
        recommendation="auto_approve",
    )

    markdown = format_as_markdown(review, confidence)

    assert "LGTM" in markdown
    assert "No issues found" in markdown or "issues" not in markdown.lower() or "0 issues" in markdown.lower()


def test_format_as_markdown_critical_issues():
    """Test formatting with critical issues."""
    review = LLMReviewResult(
        summary="Critical security issue found",
        issues=[
            ReviewIssue(
                severity="critical",
                category="security",
                file="auth.py",
                line=10,
                description="SQL injection vulnerability",
                suggestion="Use parameterized queries",
            )
        ],
        model="claude-sonnet-4-20250514",
        cost_usd=0.005,
    )
    confidence = ConfidenceResult(
        score=0.3,
        level="low",
        recommendation="request_human_review",
    )

    markdown = format_as_markdown(review, confidence)

    assert "critical" in markdown.lower()
    assert "security" in markdown.lower()
    assert "human review" in markdown.lower() or "request" in markdown.lower()
