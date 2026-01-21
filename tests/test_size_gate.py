"""Tests for size gate."""

from pr_review_agent.config import Config, LimitsConfig
from pr_review_agent.gates.size_gate import check_size
from pr_review_agent.github_client import PRData


def make_pr(lines_added: int = 10, lines_removed: int = 5, files: int = 3) -> PRData:
    """Create test PR data."""
    return PRData(
        owner="test",
        repo="repo",
        number=1,
        title="Test",
        author="user",
        description="",
        diff="",
        files_changed=["file.py"] * files,
        lines_added=lines_added,
        lines_removed=lines_removed,
        base_branch="main",
        head_branch="feature",
        url="",
    )


def test_size_gate_passes_small_pr():
    """Small PR should pass size gate."""
    config = Config(limits=LimitsConfig(max_lines_changed=500, max_files_changed=20))
    pr = make_pr(lines_added=50, lines_removed=10, files=3)

    result = check_size(pr, config)

    assert result.passed is True
    assert result.lines_changed == 60
    assert result.files_changed == 3


def test_size_gate_fails_too_many_lines():
    """PR with too many lines should fail."""
    config = Config(limits=LimitsConfig(max_lines_changed=100, max_files_changed=20))
    pr = make_pr(lines_added=200, lines_removed=50, files=5)

    result = check_size(pr, config)

    assert result.passed is False
    assert "250 lines" in result.reason
    assert result.recommendation is not None


def test_size_gate_fails_too_many_files():
    """PR with too many files should fail."""
    config = Config(limits=LimitsConfig(max_lines_changed=500, max_files_changed=5))
    pr = make_pr(lines_added=10, lines_removed=5, files=10)

    result = check_size(pr, config)

    assert result.passed is False
    assert "10 files" in result.reason
