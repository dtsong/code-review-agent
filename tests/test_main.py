"""Integration tests for main CLI."""

from unittest.mock import MagicMock, patch

from pr_review_agent.execution.degradation import DegradationLevel, DegradationResult
from pr_review_agent.main import main, run_review


def test_run_review_size_gate_fails():
    """Review should stop when size gate fails."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "Big PR"
    mock_pr.author = "user"
    mock_pr.description = "Large refactor"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 1000
    mock_pr.lines_removed = 500
    mock_pr.lines_changed = 1500  # Required for pre_analyzer
    mock_pr.files_changed = ["file.py"] * 30

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_client=mock_client,
        anthropic_key="fake",
        config_path=None,
    )

    assert result["size_gate_passed"] is False
    assert result["llm_called"] is False


@patch("pr_review_agent.main.DegradedReviewPipeline")
def test_run_review_full_flow(mock_pipeline_class):
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
    mock_pr.lines_changed = 60  # Required for pre_analyzer
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr

    mock_review = MagicMock()
    mock_review.summary = "LGTM - looks good to me"
    mock_review.issues = []
    mock_review.strengths = ["Good"]
    mock_review.concerns = []
    mock_review.questions = []
    mock_review.input_tokens = 100
    mock_review.output_tokens = 50
    mock_review.model = "claude-sonnet-4-20250514"
    mock_review.cost_usd = 0.001

    # Mock the degradation pipeline to return full review
    mock_pipeline = MagicMock()
    mock_pipeline.execute.return_value = DegradationResult(
        level=DegradationLevel.FULL,
        review_result=mock_review,
        gate_results={},
    )
    mock_pipeline_class.return_value = mock_pipeline

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_client=mock_client,
        anthropic_key="fake",
        config_path=None,
    )

    assert result["size_gate_passed"] is True
    assert result["llm_called"] is True
    assert result["confidence_score"] > 0


@patch("pr_review_agent.main.DegradedReviewPipeline")
def test_run_review_posts_comment(mock_pipeline_class):
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
    mock_pr.lines_changed = 60  # Required for pre_analyzer
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr
    mock_client.post_comment.return_value = "https://github.com/test/repo/pull/1#comment"

    mock_review = MagicMock()
    mock_review.summary = "LGTM - looks good to me"
    mock_review.issues = []
    mock_review.strengths = ["Good"]
    mock_review.concerns = []
    mock_review.questions = []
    mock_review.input_tokens = 100
    mock_review.output_tokens = 50
    mock_review.model = "claude-sonnet-4-20250514"
    mock_review.cost_usd = 0.001

    mock_pipeline = MagicMock()
    mock_pipeline.execute.return_value = DegradationResult(
        level=DegradationLevel.FULL,
        review_result=mock_review,
        gate_results={},
    )
    mock_pipeline_class.return_value = mock_pipeline

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_client=mock_client,
        anthropic_key="fake",
        config_path=None,
        post_comment=True,
    )

    assert result["comment_posted"] is True
    mock_client.post_comment.assert_called_once()


# --- Security gate test ---


@patch("pr_review_agent.main.run_security_scan")
def test_run_review_security_gate_fails(mock_security):
    """Security gate failure stops review before LLM."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "PR"
    mock_pr.author = "user"
    mock_pr.description = "desc"
    mock_pr.diff = "+ code"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 50
    mock_pr.lines_removed = 10
    mock_pr.lines_changed = 60
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr

    mock_security.return_value = MagicMock(passed=False, recommendation="Fix secrets")

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_client=mock_client,
        anthropic_key="fake",
        config_path=None,
    )

    assert result["security_gate_passed"] is False
    assert result["llm_called"] is False


# --- Lint gate failure test ---


def test_run_review_lint_gate_fails():
    """Lint gate failure stops review before LLM."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "PR"
    mock_pr.author = "user"
    mock_pr.description = "desc"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 50
    mock_pr.lines_removed = 10
    mock_pr.lines_changed = 60
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr

    with patch("pr_review_agent.main.run_lint") as mock_lint:
        mock_lint.return_value = MagicMock(passed=False, error_count=5, recommendation="Fix lint")

        result = run_review(
            repo="test/repo",
            pr_number=1,
            github_client=mock_client,
            anthropic_key="fake",
            config_path=None,
        )

    assert result["lint_gate_passed"] is False
    assert result["llm_called"] is False


# --- Escalation test ---


@patch("pr_review_agent.main.send_webhook")
@patch("pr_review_agent.main.should_escalate")
@patch("pr_review_agent.main.DegradedReviewPipeline")
def test_run_review_escalation_triggered(mock_pipeline_class, mock_escalate, mock_webhook):
    """Low confidence triggers escalation webhook."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "PR"
    mock_pr.author = "user"
    mock_pr.description = "desc"
    mock_pr.diff = "+ code"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 50
    mock_pr.lines_removed = 10
    mock_pr.lines_changed = 60
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr

    mock_review = MagicMock()
    mock_review.summary = "Uncertain about this change"
    mock_review.issues = []
    mock_review.model = "claude-sonnet-4-20250514"
    mock_review.cost_usd = 0.001

    mock_pipeline = MagicMock()
    mock_pipeline.execute.return_value = DegradationResult(
        level=DegradationLevel.FULL,
        review_result=mock_review,
        gate_results={},
    )
    mock_pipeline_class.return_value = mock_pipeline

    mock_escalate.return_value = True
    mock_webhook.return_value = True

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_client=mock_client,
        anthropic_key="fake",
        config_path=None,
    )

    assert result["escalation_sent"] is True
    mock_webhook.assert_called_once()


# --- Metrics tests ---


@patch("pr_review_agent.main.SupabaseLogger")
@patch("pr_review_agent.main.DegradedReviewPipeline")
def test_run_review_metrics_logged(mock_pipeline_class, mock_logger_class):
    """Metrics logged to Supabase when configured."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "PR"
    mock_pr.author = "user"
    mock_pr.description = "desc"
    mock_pr.diff = "+ code"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 50
    mock_pr.lines_removed = 10
    mock_pr.lines_changed = 60
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr

    mock_review = MagicMock()
    mock_review.summary = "LGTM - all looks good to me"
    mock_review.issues = []
    mock_review.model = "claude-sonnet-4-20250514"
    mock_review.cost_usd = 0.001

    mock_pipeline = MagicMock()
    mock_pipeline.execute.return_value = DegradationResult(
        level=DegradationLevel.FULL,
        review_result=mock_review,
        gate_results={},
    )
    mock_pipeline_class.return_value = mock_pipeline

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_client=mock_client,
        anthropic_key="fake",
        config_path=None,
        supabase_url="http://localhost",
        supabase_key="key",
    )

    assert result["metrics_logged"] is True
    mock_logger_class.assert_called_once_with("http://localhost", "key")


@patch("pr_review_agent.main.SupabaseLogger")
@patch("pr_review_agent.main.DegradedReviewPipeline")
def test_run_review_metrics_failure(mock_pipeline_class, mock_logger_class):
    """Metrics failure sets metrics_logged=False without raising."""
    mock_pr = MagicMock()
    mock_pr.owner = "test"
    mock_pr.repo = "repo"
    mock_pr.number = 1
    mock_pr.title = "PR"
    mock_pr.author = "user"
    mock_pr.description = "desc"
    mock_pr.diff = "+ code"
    mock_pr.url = "https://github.com/test/repo/pull/1"
    mock_pr.lines_added = 50
    mock_pr.lines_removed = 10
    mock_pr.lines_changed = 60
    mock_pr.files_changed = ["file.py"]

    mock_client = MagicMock()
    mock_client.fetch_pr.return_value = mock_pr

    mock_review = MagicMock()
    mock_review.summary = "LGTM - all looks good to me"
    mock_review.issues = []
    mock_review.model = "claude-sonnet-4-20250514"
    mock_review.cost_usd = 0.001

    mock_pipeline = MagicMock()
    mock_pipeline.execute.return_value = DegradationResult(
        level=DegradationLevel.FULL,
        review_result=mock_review,
        gate_results={},
    )
    mock_pipeline_class.return_value = mock_pipeline

    mock_logger_class.side_effect = Exception("connection failed")

    result = run_review(
        repo="test/repo",
        pr_number=1,
        github_client=mock_client,
        anthropic_key="fake",
        config_path=None,
        supabase_url="http://localhost",
        supabase_key="key",
    )

    assert result["metrics_logged"] is False


# --- CLI main() tests ---


@patch("pr_review_agent.main.run_review")
@patch("pr_review_agent.main.GitHubClient")
def test_main_with_github_token(mock_gh_class, mock_run):
    """main() uses PAT auth when GITHUB_TOKEN set."""
    mock_run.return_value = {"llm_called": True}

    env = {
        "GITHUB_TOKEN": "ghp_test",
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }
    with (
        patch.dict("os.environ", env, clear=True),
        patch("sys.argv", ["pr-review-agent", "--repo", "o/r", "--pr", "1"]),
    ):
        exit_code = main()

    assert exit_code == 0
    mock_gh_class.assert_called_once_with("ghp_test")
    mock_run.assert_called_once()


@patch("pr_review_agent.main.run_review")
@patch("pr_review_agent.main.GitHubClient")
def test_main_with_app_credentials(mock_gh_class, mock_run):
    """main() uses GitHub App auth when app credentials set."""
    mock_run.return_value = {"llm_called": True}

    env = {
        "GITHUB_APP_ID": "123",
        "GITHUB_APP_INSTALLATION_ID": "456",
        "GITHUB_APP_PRIVATE_KEY_BASE64": (
            "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
        ),
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }
    with (
        patch.dict("os.environ", env, clear=True),
        patch("sys.argv", ["pr-review-agent", "--repo", "o/r", "--pr", "1"]),
    ):
        exit_code = main()

    assert exit_code == 0
    mock_gh_class.from_app_credentials.assert_called_once()


def test_main_no_github_creds():
    """main() returns 1 when no GitHub credentials."""
    env = {"ANTHROPIC_API_KEY": "sk-ant-test"}
    with (
        patch.dict("os.environ", env, clear=True),
        patch("sys.argv", ["pr-review-agent", "--repo", "o/r", "--pr", "1"]),
    ):
        exit_code = main()

    assert exit_code == 1


@patch("pr_review_agent.main.run_review")
@patch("pr_review_agent.main.GitHubClient")
def test_main_exception_handling(mock_gh_class, mock_run):
    """main() returns 1 when run_review raises."""
    mock_run.side_effect = Exception("Something went wrong")

    env = {
        "GITHUB_TOKEN": "ghp_test",
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }
    with (
        patch.dict("os.environ", env, clear=True),
        patch("sys.argv", ["pr-review-agent", "--repo", "o/r", "--pr", "1"]),
    ):
        exit_code = main()

    assert exit_code == 1
