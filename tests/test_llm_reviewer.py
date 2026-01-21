"""Tests for LLM reviewer."""

from unittest.mock import MagicMock, patch

from pr_review_agent.config import Config
from pr_review_agent.review.llm_reviewer import LLMReviewer, LLMReviewResult, ReviewIssue


def test_review_issue_dataclass():
    """Test ReviewIssue can be instantiated."""
    issue = ReviewIssue(
        severity="major",
        category="logic",
        file="test.py",
        line=10,
        description="Potential bug",
        suggestion="Fix it",
    )
    assert issue.severity == "major"
    assert issue.line == 10


def test_calculate_cost():
    """Test cost calculation for different models."""
    reviewer = LLMReviewer.__new__(LLMReviewer)

    # Sonnet pricing
    cost = reviewer._calculate_cost("claude-sonnet-4-20250514", 1000, 500)
    expected = (1000 * 0.003 / 1000) + (500 * 0.015 / 1000)
    assert abs(cost - expected) < 0.0001

    # Haiku pricing
    cost = reviewer._calculate_cost("claude-haiku-4-20250514", 1000, 500)
    expected = (1000 * 0.00025 / 1000) + (500 * 0.00125 / 1000)
    assert abs(cost - expected) < 0.0001


@patch("pr_review_agent.review.llm_reviewer.Anthropic")
def test_review_returns_structured_result(mock_anthropic_class):
    """Test that review returns structured LLMReviewResult."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='''{
        "summary": "Overall good PR",
        "issues": [
            {
                "severity": "minor",
                "category": "style",
                "file": "test.py",
                "line": 5,
                "description": "Consider better naming",
                "suggestion": "Rename to be more descriptive"
            }
        ],
        "strengths": ["Good structure"],
        "concerns": [],
        "questions": []
    }''')]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client

    reviewer = LLMReviewer("fake-key")
    config = Config()

    result = reviewer.review(
        diff="+ new code",
        pr_description="Test PR",
        model="claude-sonnet-4-20250514",
        config=config,
    )

    assert isinstance(result, LLMReviewResult)
    assert result.summary == "Overall good PR"
    assert len(result.issues) == 1
    assert result.issues[0].severity == "minor"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
