"""Integration tests for main CLI."""

from unittest.mock import MagicMock, patch

from pr_review_agent.main import run_review


@patch("pr_review_agent.main.GitHubClient")
def test_run_review_size_gate_fails(mock_github_class):
    """Review should stop when size gate fails."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "Big PR"
    mock_pr.author = "user"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 1000
    mock_pr.lines_removed = 500
    mock_pr.files_changed = ["file.py"] * 30

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr
    mock_github_class.return_value = mock_client

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_token="fake",
        anthropic_key="fake",
        config_path=None,
    )

    assert result["size_gate_passed"] is False
    assert result["llm_called"] is False


@patch("pr_review_agent.main.LLMReviewer")
@patch("pr_review_agent.main.GitHubClient")
def test_run_review_full_flow(mock_github_class, mock_llm_class):
    """Full review flow with passing gates."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "Good PR"
    mock_pr.author = "user"
    mock_pr.description = "A good PR"
    mock_pr.diff = "+ new code"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 50
    mock_pr.lines_removed = 10
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr
    mock_github_class.return_value = mock_client

    mock_review = MagicMock()
    mock_review.summary = "LGTM"
    mock_review.issues = []
    mock_review.strengths = ["Good"]
    mock_review.concerns = []
    mock_review.questions = []
    mock_review.input_tokens = 100
    mock_review.output_tokens = 50
    mock_review.model = "claude-sonnet-4-20250514"
    mock_review.cost_usd = 0.001

    mock_reviewer = MagicMock()
    mock_reviewer.review.return_value = mock_review
    mock_llm_class.return_value = mock_reviewer

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_token="fake",
        anthropic_key="fake",
        config_path=None,
    )

    assert result["size_gate_passed"] is True
    assert result["llm_called"] is True
    assert result["confidence_score"] > 0


@patch("pr_review_agent.main.LLMReviewer")
@patch("pr_review_agent.main.GitHubClient")
def test_run_review_posts_comment(mock_github_class, mock_llm_class):
    """Review should post comment when post_comment=True."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "Good PR"
    mock_pr.author = "user"
    mock_pr.description = "A good PR"
    mock_pr.diff = "+ new code"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 50
    mock_pr.lines_removed = 10
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr
    mock_client.post_comment.return_value = "https://github.com/test/repo/pull/1#comment"
    mock_github_class.return_value = mock_client

    mock_review = MagicMock()
    mock_review.summary = "LGTM"
    mock_review.issues = []
    mock_review.strengths = ["Good"]
    mock_review.concerns = []
    mock_review.questions = []
    mock_review.input_tokens = 100
    mock_review.output_tokens = 50
    mock_review.model = "claude-sonnet-4-20250514"
    mock_review.cost_usd = 0.001

    mock_reviewer = MagicMock()
    mock_reviewer.review.return_value = mock_review
    mock_llm_class.return_value = mock_reviewer

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_token="fake",
        anthropic_key="fake",
        config_path=None,
        post_comment=True,
    )

    assert result["comment_posted"] is True
    mock_client.post_comment.assert_called_once()
