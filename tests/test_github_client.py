"""Tests for GitHub client."""

from unittest.mock import MagicMock, patch

import pytest

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


@patch("pr_review_agent.github_client.Github")
def test_post_comment(mock_github_class):
    """Test posting a comment to a PR."""
    mock_pr = MagicMock()
    mock_pr.create_issue_comment.return_value = MagicMock(
        html_url="https://github.com/owner/repo/pull/1#issuecomment-123"
    )

    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr

    mock_github = MagicMock()
    mock_github.get_repo.return_value = mock_repo
    mock_github_class.return_value = mock_github

    client = GitHubClient("fake-token")
    url = client.post_comment("owner", "repo", 1, "Test comment")

    assert url == "https://github.com/owner/repo/pull/1#issuecomment-123"
    mock_pr.create_issue_comment.assert_called_once_with("Test comment")


# --- from_app_credentials tests ---


@patch("pr_review_agent.github_client.requests.post")
@patch("pr_review_agent.github_client.jwt.encode")
@patch("pr_review_agent.github_client.Github")
def test_from_app_credentials_success(mock_github_class, mock_jwt, mock_post):
    """Successful GitHub App authentication returns a client."""
    mock_jwt.return_value = "fake-jwt-token"
    mock_post.return_value = MagicMock(
        status_code=200, ok=True, json=lambda: {"token": "ghs_install_token"}
    )

    client = GitHubClient.from_app_credentials(
        app_id="12345",
        installation_id="67890",
        private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
    )

    assert isinstance(client, GitHubClient)
    mock_jwt.assert_called_once()
    mock_github_class.assert_called_once_with("ghs_install_token")


def test_from_app_credentials_invalid_key():
    """Invalid PEM key raises ValueError."""
    with pytest.raises(ValueError, match="Invalid private key format"):
        GitHubClient.from_app_credentials(
            app_id="12345",
            installation_id="67890",
            private_key="not-a-valid-pem-key",
        )


@patch("pr_review_agent.github_client.jwt.encode")
def test_from_app_credentials_jwt_failure(mock_jwt):
    """JWT encoding failure raises ValueError."""
    mock_jwt.side_effect = Exception("bad key")

    with pytest.raises(ValueError, match="Failed to sign JWT"):
        GitHubClient.from_app_credentials(
            app_id="12345",
            installation_id="67890",
            private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        )


@patch("pr_review_agent.github_client.requests.post")
@patch("pr_review_agent.github_client.jwt.encode")
def test_from_app_credentials_401(mock_jwt, mock_post):
    """401 response raises ValueError with auth hint."""
    mock_jwt.return_value = "fake-jwt"
    mock_post.return_value = MagicMock(status_code=401, ok=False)

    with pytest.raises(ValueError, match="401 Unauthorized"):
        GitHubClient.from_app_credentials(
            app_id="12345",
            installation_id="67890",
            private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        )


@patch("pr_review_agent.github_client.requests.post")
@patch("pr_review_agent.github_client.jwt.encode")
def test_from_app_credentials_404(mock_jwt, mock_post):
    """404 response raises ValueError with installation hint."""
    mock_jwt.return_value = "fake-jwt"
    mock_post.return_value = MagicMock(status_code=404, ok=False)

    with pytest.raises(ValueError, match="Installation not found"):
        GitHubClient.from_app_credentials(
            app_id="12345",
            installation_id="67890",
            private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        )


@patch("pr_review_agent.github_client.requests.post")
@patch("pr_review_agent.github_client.jwt.encode")
def test_from_app_credentials_500(mock_jwt, mock_post):
    """Generic API error raises ValueError."""
    mock_jwt.return_value = "fake-jwt"
    mock_post.return_value = MagicMock(status_code=500, ok=False, text="Internal Server Error")

    with pytest.raises(ValueError, match="GitHub API error"):
        GitHubClient.from_app_credentials(
            app_id="12345",
            installation_id="67890",
            private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        )


# --- post_review_comments tests ---


@patch("pr_review_agent.github_client.Github")
def test_post_review_comments_success(mock_github_class):
    """post_review_comments creates a review with inline comments."""
    mock_review = MagicMock(html_url="https://github.com/o/r/pull/1#pullrequestreview-1")
    mock_commit = MagicMock()
    mock_commits = MagicMock()
    mock_commits.reversed = [mock_commit]
    mock_pr = MagicMock()
    mock_pr.get_commits.return_value = mock_commits
    mock_pr.create_review.return_value = mock_review
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_github = MagicMock()
    mock_github.get_repo.return_value = mock_repo
    mock_github_class.return_value = mock_github

    client = GitHubClient("fake-token")
    comments = [{"path": "file.py", "body": "Fix this", "line": 10}]
    url = client.post_review_comments("owner", "repo", 1, comments, body="Review")

    assert url == "https://github.com/o/r/pull/1#pullrequestreview-1"
    mock_pr.create_review.assert_called_once()
    call_kwargs = mock_pr.create_review.call_args[1]
    assert call_kwargs["event"] == "COMMENT"
    assert len(call_kwargs["comments"]) == 1


@patch("pr_review_agent.github_client.Github")
def test_post_review_comments_with_start_line(mock_github_class):
    """Multi-line comment includes start_line when different from line."""
    mock_review = MagicMock(html_url="https://github.com/o/r/pull/1#review")
    mock_commit = MagicMock()
    mock_commits = MagicMock()
    mock_commits.reversed = [mock_commit]
    mock_pr = MagicMock()
    mock_pr.get_commits.return_value = mock_commits
    mock_pr.create_review.return_value = mock_review
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_github = MagicMock()
    mock_github.get_repo.return_value = mock_repo
    mock_github_class.return_value = mock_github

    client = GitHubClient("fake-token")
    comments = [{"path": "file.py", "body": "Fix this", "line": 15, "start_line": 10}]
    client.post_review_comments("owner", "repo", 1, comments)

    call_kwargs = mock_pr.create_review.call_args[1]
    assert call_kwargs["comments"][0]["start_line"] == 10


@patch("pr_review_agent.github_client.Github")
def test_post_review_comments_start_line_equals_line(mock_github_class):
    """start_line omitted when equal to line."""
    mock_review = MagicMock(html_url="https://github.com/o/r/pull/1#review")
    mock_commit = MagicMock()
    mock_commits = MagicMock()
    mock_commits.reversed = [mock_commit]
    mock_pr = MagicMock()
    mock_pr.get_commits.return_value = mock_commits
    mock_pr.create_review.return_value = mock_review
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_github = MagicMock()
    mock_github.get_repo.return_value = mock_repo
    mock_github_class.return_value = mock_github

    client = GitHubClient("fake-token")
    comments = [{"path": "file.py", "body": "Fix this", "line": 10, "start_line": 10}]
    client.post_review_comments("owner", "repo", 1, comments)

    call_kwargs = mock_pr.create_review.call_args[1]
    assert "start_line" not in call_kwargs["comments"][0]
