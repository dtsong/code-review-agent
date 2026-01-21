"""Tests for confidence scoring."""

from pr_review_agent.config import ConfidenceConfig, Config
from pr_review_agent.github_client import PRData
from pr_review_agent.review.confidence import calculate_confidence
from pr_review_agent.review.llm_reviewer import LLMReviewResult, ReviewIssue


def make_pr() -> PRData:
    """Create test PR."""
    return PRData(
        owner="test",
        repo="repo",
        number=1,
        title="Test",
        author="user",
        description="Good description",
        diff="",
        files_changed=["file.py"],
        lines_added=50,
        lines_removed=10,
        base_branch="main",
        head_branch="feature",
        url="",
    )


def test_high_confidence_no_issues():
    """No issues should result in high confidence."""
    review = LLMReviewResult(
        summary="LGTM",
        issues=[],
        strengths=["Clean code"],
    )
    config = Config(confidence=ConfidenceConfig(high=0.8, low=0.5))

    result = calculate_confidence(review, make_pr(), config)

    assert result.score >= 0.8
    assert result.level == "high"
    assert result.recommendation == "auto_approve"


def test_low_confidence_critical_issue():
    """Critical issues should result in low confidence."""
    review = LLMReviewResult(
        summary="Found critical bug",
        issues=[
            ReviewIssue(
                severity="critical",
                category="logic",
                file="test.py",
                line=10,
                description="Null pointer",
                suggestion="Add null check",
            )
        ],
    )
    config = Config(confidence=ConfidenceConfig(high=0.8, low=0.5))

    result = calculate_confidence(review, make_pr(), config)

    assert result.score < 0.5
    assert result.level == "low"
    assert result.recommendation == "request_human_review"


def test_medium_confidence_minor_issues():
    """Minor issues should result in medium confidence."""
    review = LLMReviewResult(
        summary="Some suggestions",
        issues=[
            ReviewIssue(
                severity="suggestion",
                category="style",
                file="test.py",
                line=5,
                description="Consider rename",
                suggestion="Use better name",
            )
        ],
    )
    config = Config(confidence=ConfidenceConfig(high=0.8, low=0.5))

    result = calculate_confidence(review, make_pr(), config)

    assert 0.5 <= result.score < 0.8
    assert result.level == "medium"
    assert result.recommendation == "comment_only"
