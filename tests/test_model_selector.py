"""Tests for model selector."""

from pr_review_agent.config import Config, LLMConfig
from pr_review_agent.github_client import PRData
from pr_review_agent.review.model_selector import select_model


def make_pr(lines_added: int, lines_removed: int) -> PRData:
    """Create test PR."""
    return PRData(
        owner="test",
        repo="repo",
        number=1,
        title="Test",
        author="user",
        description="",
        diff="",
        files_changed=[],
        lines_added=lines_added,
        lines_removed=lines_removed,
        base_branch="main",
        head_branch="feature",
        url="",
    )


def test_select_simple_model_for_small_pr():
    """Small PRs should use the simple (cheaper) model."""
    config = Config(llm=LLMConfig(
        simple_model="claude-haiku-4-20250514",
        default_model="claude-sonnet-4-20250514",
        simple_threshold_lines=50,
    ))
    pr = make_pr(lines_added=20, lines_removed=10)

    model = select_model(pr, config)

    assert model == "claude-haiku-4-20250514"


def test_select_default_model_for_large_pr():
    """Larger PRs should use the default (smarter) model."""
    config = Config(llm=LLMConfig(
        simple_model="claude-haiku-4-20250514",
        default_model="claude-sonnet-4-20250514",
        simple_threshold_lines=50,
    ))
    pr = make_pr(lines_added=100, lines_removed=50)

    model = select_model(pr, config)

    assert model == "claude-sonnet-4-20250514"


def test_select_model_at_threshold():
    """PRs at exactly the threshold should use default model."""
    config = Config(llm=LLMConfig(
        simple_model="claude-haiku-4-20250514",
        default_model="claude-sonnet-4-20250514",
        simple_threshold_lines=50,
    ))
    pr = make_pr(lines_added=25, lines_removed=25)

    model = select_model(pr, config)

    assert model == "claude-sonnet-4-20250514"
