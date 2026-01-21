"""Tests for GitHub client."""

from unittest.mock import MagicMock, patch

from pr_review_agent.github_client import GitHubClient, PRData


def test_pr_data_dataclass():
    """Test PRData dataclass can be instantiated."""
    pr = PRData(
        owner="test",
        repo="repo",
        number=1,
        title="Test PR",
        author="author",
        description="Description",
        diff="diff content",
        files_changed=["file1.py"],
        lines_added=10,
        lines_removed=5,
        base_branch="main",
        head_branch="feature",
        url="https://github.com/test/repo/pull/1",
    )
    assert pr.owner == "test"
    assert pr.number == 1
    assert pr.lines_added == 10


@patch("pr_review_agent.github_client.Github")
def test_fetch_pr(mock_github_class):
    """Test fetching PR data from GitHub."""
    # Setup mock
    mock_pr = MagicMock()
    mock_pr.title = "Test PR"
    mock_pr.user.login = "testuser"
    mock_pr.body = "PR description"
    mock_pr.base.ref = "main"
    mock_pr.head.ref = "feature-branch"
    mock_pr.html_url = "https://github.com/owner/repo/pull/1"
    mock_pr.additions = 50
    mock_pr.deletions = 10

    mock_file = MagicMock()
    mock_file.filename = "src/test.py"
    mock_file.patch = "@@ -1,3 +1,5 @@\n+new line"
    mock_pr.get_files.return_value = [mock_file]

    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr

    mock_github = MagicMock()
    mock_github.get_repo.return_value = mock_repo
    mock_github_class.return_value = mock_github

    # Test
    client = GitHubClient("fake-token")
    pr_data = client.fetch_pr("owner", "repo", 1)

    assert pr_data.title == "Test PR"
    assert pr_data.author == "testuser"
    assert pr_data.lines_added == 50
    assert pr_data.lines_removed == 10
    assert "src/test.py" in pr_data.files_changed
