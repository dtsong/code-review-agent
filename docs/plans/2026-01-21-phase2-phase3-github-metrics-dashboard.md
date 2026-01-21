# Phase 2 & 3: GitHub Comments, Metrics & Dashboard

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add GitHub PR comment posting, Supabase metrics logging, and a Next.js dashboard to visualize review data.

**Architecture:** Phase 2 extends the existing CLI to post formatted markdown comments to GitHub PRs. Phase 3 adds a metrics logger that sends review data to Supabase, plus a Next.js dashboard for visualization.

**Tech Stack:** PyGithub (comments), supabase-py (metrics), Next.js + Recharts (dashboard), Vercel (deploy)

---

## Phase 2: GitHub Integration

### Task 1: Add supabase dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add supabase to dependencies**

Edit `pyproject.toml` to add supabase:
```toml
dependencies = [
    "anthropic>=0.40.0",
    "pygithub>=2.5.0",
    "pyyaml>=6.0",
    "supabase>=2.0.0",
]
```

**Step 2: Sync dependencies**

Run:
```bash
uv sync
```

Expected: supabase and dependencies installed

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add supabase dependency"
```

---

### Task 2: GitHub Comment Formatter

**Files:**
- Create: `src/pr_review_agent/output/github_comment.py`
- Create: `tests/test_github_comment.py`

**Step 1: Write the failing test**

Create `tests/test_github_comment.py`:
```python
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_github_comment.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/output/github_comment.py`:
```python
"""GitHub comment formatting and posting."""

from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import LLMReviewResult


def format_as_markdown(
    review: LLMReviewResult,
    confidence: ConfidenceResult,
) -> str:
    """Format review results as GitHub-flavored markdown."""
    lines = []

    # Header
    lines.append("## 🤖 AI Code Review")
    lines.append("")

    # Summary
    lines.append("### Summary")
    lines.append(review.summary)
    lines.append("")

    # Confidence
    confidence_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(
        confidence.level, "⚪"
    )
    lines.append(f"**Confidence:** {confidence_emoji} {confidence.score:.2f} ({confidence.level})")
    if confidence.level == "low":
        lines.append("⚠️ *This PR may require human review*")
    lines.append("")

    # Strengths
    if review.strengths:
        lines.append("### ✅ Strengths")
        for strength in review.strengths:
            lines.append(f"- {strength}")
        lines.append("")

    # Issues
    if review.issues:
        lines.append("### 🔍 Issues Found")
        lines.append("")

        # Group by severity
        severity_order = ["critical", "major", "minor", "suggestion"]
        severity_emoji = {
            "critical": "🔴",
            "major": "🟠",
            "minor": "🟡",
            "suggestion": "💡",
        }

        for severity in severity_order:
            severity_issues = [i for i in review.issues if i.severity == severity]
            if severity_issues:
                lines.append(f"#### {severity_emoji.get(severity, '•')} {severity.title()} ({len(severity_issues)})")
                lines.append("")
                for issue in severity_issues:
                    location = f"`{issue.file}:{issue.line}`" if issue.line else f"`{issue.file}`"
                    lines.append(f"**{location}** - {issue.category}")
                    lines.append(f"> {issue.description}")
                    if issue.suggestion:
                        lines.append(f"> 💡 *Suggestion: {issue.suggestion}*")
                    lines.append("")
    else:
        lines.append("### ✅ No Issues Found")
        lines.append("")

    # Concerns
    if review.concerns:
        lines.append("### ⚠️ Concerns")
        for concern in review.concerns:
            lines.append(f"- {concern}")
        lines.append("")

    # Questions
    if review.questions:
        lines.append("### ❓ Questions")
        for question in review.questions:
            lines.append(f"- {question}")
        lines.append("")

    # Footer with metadata
    lines.append("---")
    lines.append(f"<sub>Model: `{review.model}` | Cost: ${review.cost_usd:.4f} | ")
    lines.append(f"Tokens: {review.input_tokens} in / {review.output_tokens} out</sub>")

    return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_github_comment.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/output/github_comment.py tests/test_github_comment.py
git commit -m "feat: add GitHub comment markdown formatter"
```

---

### Task 3: Add post_comment to GitHubClient

**Files:**
- Modify: `src/pr_review_agent/github_client.py`
- Modify: `tests/test_github_client.py`

**Step 1: Write the failing test**

Add to `tests/test_github_client.py`:
```python
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_github_client.py::test_post_comment -v
```

Expected: FAIL with `AttributeError: 'GitHubClient' object has no attribute 'post_comment'`

**Step 3: Add post_comment method**

Add to `src/pr_review_agent/github_client.py`:
```python
    def post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> str:
        """Post a comment on a PR. Returns the comment URL."""
        repo_obj = self.client.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pr_number)
        comment = pr.create_issue_comment(body)
        return comment.html_url
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_github_client.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/github_client.py tests/test_github_client.py
git commit -m "feat: add post_comment method to GitHubClient"
```

---

### Task 4: Wire up --post-comment flag

**Files:**
- Modify: `src/pr_review_agent/main.py`
- Modify: `tests/test_main.py`

**Step 1: Write the failing test**

Add to `tests/test_main.py`:
```python
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_main.py::test_run_review_posts_comment -v
```

Expected: FAIL (run_review doesn't accept post_comment parameter)

**Step 3: Update run_review and main**

Update `src/pr_review_agent/main.py`:

1. Add import at top:
```python
from pr_review_agent.output.github_comment import format_as_markdown
```

2. Update run_review signature:
```python
def run_review(
    repo: str,
    pr_number: int,
    github_token: str,
    anthropic_key: str,
    config_path: Path | None,
    post_comment: bool = False,
) -> dict[str, Any]:
```

3. Add to result dict initialization:
```python
    result: dict[str, Any] = {
        "pr_number": pr_number,
        "repo": repo,
        "size_gate_passed": False,
        "lint_gate_passed": False,
        "llm_called": False,
        "confidence_score": 0.0,
        "comment_posted": False,
    }
```

4. After `print_results`, before final return, add:
```python
    # Post comment to GitHub if requested
    if post_comment and review_result:
        comment_body = format_as_markdown(review_result, confidence)
        comment_url = github.post_comment(owner, repo_name, pr_number, comment_body)
        result["comment_posted"] = True
        result["comment_url"] = comment_url
        print(f"\nComment posted: {comment_url}")
```

5. Update main() to pass the flag:
```python
        run_review(
            repo=args.repo,
            pr_number=args.pr,
            github_token=github_token,
            anthropic_key=anthropic_key,
            config_path=Path(args.config) if args.config else None,
            post_comment=args.post_comment,
        )
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_main.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/main.py tests/test_main.py
git commit -m "feat: wire up --post-comment flag to post GitHub comments"
```

---

### Task 5: Create GitHub Action workflow

**Files:**
- Create: `.github/workflows/pr-review.yml`

**Step 1: Create the workflow file**

Create `.github/workflows/pr-review.yml`:
```yaml
name: AI PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  ai-review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

      - name: Run PR Review Agent
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: |
          uv run pr-review-agent \
            --repo ${{ github.repository }} \
            --pr ${{ github.event.pull_request.number }} \
            --post-comment
```

**Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/pr-review.yml
git commit -m "feat: add GitHub Action workflow for PR review"
```

---

## Phase 3: Metrics & Dashboard

### Task 6: Supabase Logger

**Files:**
- Create: `src/pr_review_agent/metrics/__init__.py`
- Create: `src/pr_review_agent/metrics/supabase_logger.py`
- Create: `tests/test_supabase_logger.py`

**Step 1: Write the failing test**

Create `tests/test_supabase_logger.py`:
```python
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_supabase_logger.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/metrics/__init__.py`:
```python
"""Metrics module for logging review data."""

from pr_review_agent.metrics.supabase_logger import SupabaseLogger

__all__ = ["SupabaseLogger"]
```

Create `src/pr_review_agent/metrics/supabase_logger.py`:
```python
"""Supabase metrics logger."""

from supabase import create_client, Client

from pr_review_agent.gates.lint_gate import LintGateResult
from pr_review_agent.gates.size_gate import SizeGateResult
from pr_review_agent.github_client import PRData
from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import LLMReviewResult


class SupabaseLogger:
    """Log review metrics to Supabase."""

    def __init__(self, url: str, key: str):
        """Initialize with Supabase credentials."""
        self.client: Client = create_client(url, key)

    def log_review(
        self,
        pr: PRData,
        size_result: SizeGateResult,
        lint_result: LintGateResult | None,
        review_result: LLMReviewResult | None,
        confidence: ConfidenceResult | None,
        outcome: str,
        duration_ms: int,
    ) -> str | None:
        """Log complete review event to Supabase.

        Returns the inserted row ID, or None if logging fails.
        """
        # Build the data payload
        data = {
            # PR identification
            "repo_owner": pr.owner,
            "repo_name": pr.repo,
            "pr_number": pr.number,
            "pr_title": pr.title,
            "pr_author": pr.author,
            "pr_url": pr.url,
            # Diff stats
            "lines_added": pr.lines_added,
            "lines_removed": pr.lines_removed,
            "files_changed": len(pr.files_changed),
            # Gate results
            "size_gate_passed": size_result.passed,
            "lint_gate_passed": lint_result.passed if lint_result else None,
            "lint_errors_count": lint_result.error_count if lint_result else None,
            # LLM review
            "llm_called": review_result is not None,
            "model_used": review_result.model if review_result else None,
            "input_tokens": review_result.input_tokens if review_result else None,
            "output_tokens": review_result.output_tokens if review_result else None,
            "cost_usd": review_result.cost_usd if review_result else None,
            # Review results
            "confidence_score": confidence.score if confidence else None,
            "issues_found": (
                [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "file": i.file,
                        "line": i.line,
                        "description": i.description,
                    }
                    for i in review_result.issues
                ]
                if review_result
                else None
            ),
            # Outcome
            "outcome": outcome,
            "escalated_to_human": confidence.level == "low" if confidence else False,
            # Timing
            "review_duration_ms": duration_ms,
        }

        try:
            result = self.client.table("review_events").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            # Don't fail the review if metrics logging fails
            return None
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_supabase_logger.py -v
```

Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/metrics/ tests/test_supabase_logger.py
git commit -m "feat: add Supabase metrics logger"
```

---

### Task 7: Wire up metrics logging in main

**Files:**
- Modify: `src/pr_review_agent/main.py`

**Step 1: Update main.py to log metrics**

Add import:
```python
from pr_review_agent.metrics.supabase_logger import SupabaseLogger
```

Update run_review signature:
```python
def run_review(
    repo: str,
    pr_number: int,
    github_token: str,
    anthropic_key: str,
    config_path: Path | None,
    post_comment: bool = False,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
) -> dict[str, Any]:
```

After the comment posting section, before the final return, add:
```python
    # Log metrics to Supabase if configured
    if supabase_url and supabase_key:
        try:
            logger = SupabaseLogger(supabase_url, supabase_key)
            outcome = "approved" if confidence.level == "high" else (
                "changes_requested" if confidence.level == "medium" else "escalated"
            )
            logger.log_review(
                pr=pr,
                size_result=size_result,
                lint_result=lint_result,
                review_result=review_result,
                confidence=confidence,
                outcome=outcome,
                duration_ms=result["duration_ms"],
            )
            result["metrics_logged"] = True
        except Exception:
            result["metrics_logged"] = False
```

Update main() to read Supabase env vars:
```python
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
```

And pass them to run_review:
```python
        run_review(
            repo=args.repo,
            pr_number=args.pr,
            github_token=github_token,
            anthropic_key=anthropic_key,
            config_path=Path(args.config) if args.config else None,
            post_comment=args.post_comment,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
        )
```

**Step 2: Run all tests**

Run:
```bash
uv run pytest -v
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/pr_review_agent/main.py
git commit -m "feat: wire up Supabase metrics logging"
```

---

### Task 8: Create Supabase SQL schema file

**Files:**
- Create: `database/schema.sql`

**Step 1: Create the schema file**

Create `database/schema.sql`:
```sql
-- PR Review Agent - Supabase Schema
-- Run this in your Supabase SQL editor to set up the database

-- Table: review_events
CREATE TABLE IF NOT EXISTS review_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  -- PR identification
  repo_owner TEXT NOT NULL,
  repo_name TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  pr_title TEXT,
  pr_author TEXT,
  pr_url TEXT,

  -- Diff stats
  lines_added INTEGER,
  lines_removed INTEGER,
  files_changed INTEGER,

  -- Gate results
  size_gate_passed BOOLEAN,
  lint_gate_passed BOOLEAN,
  lint_errors_count INTEGER,

  -- LLM review (nullable if gated)
  llm_called BOOLEAN DEFAULT FALSE,
  model_used TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_usd DECIMAL(10, 6),

  -- Review results
  confidence_score DECIMAL(3, 2),
  issues_found JSONB,

  -- Outcome
  outcome TEXT,
  escalated_to_human BOOLEAN DEFAULT FALSE,

  -- Timing
  review_duration_ms INTEGER
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_review_events_repo
  ON review_events(repo_owner, repo_name);
CREATE INDEX IF NOT EXISTS idx_review_events_created
  ON review_events(created_at);
CREATE INDEX IF NOT EXISTS idx_review_events_author
  ON review_events(pr_author);

-- View: Daily summary for dashboard
CREATE OR REPLACE VIEW daily_review_summary AS
SELECT
  DATE(created_at) as review_date,
  COUNT(*) as total_reviews,
  SUM(CASE WHEN llm_called THEN 1 ELSE 0 END) as llm_reviews,
  SUM(CASE WHEN NOT size_gate_passed OR NOT COALESCE(lint_gate_passed, TRUE) THEN 1 ELSE 0 END) as gated_reviews,
  COALESCE(SUM(cost_usd), 0) as total_cost,
  AVG(confidence_score) as avg_confidence,
  SUM(CASE WHEN escalated_to_human THEN 1 ELSE 0 END) as escalations
FROM review_events
GROUP BY DATE(created_at)
ORDER BY review_date DESC;

-- View: Stats by repository
CREATE OR REPLACE VIEW repo_stats AS
SELECT
  repo_owner,
  repo_name,
  COUNT(*) as total_reviews,
  COALESCE(SUM(cost_usd), 0) as total_cost,
  AVG(confidence_score) as avg_confidence,
  SUM(CASE WHEN escalated_to_human THEN 1 ELSE 0 END) as escalations
FROM review_events
GROUP BY repo_owner, repo_name
ORDER BY total_reviews DESC;
```

**Step 2: Commit**

```bash
mkdir -p database
git add database/schema.sql
git commit -m "docs: add Supabase schema SQL"
```

---

### Task 9: Create Next.js Dashboard

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/next.config.js`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/src/app/layout.tsx`
- Create: `dashboard/src/app/page.tsx`
- Create: `dashboard/src/lib/supabase.ts`
- Create: `dashboard/.env.example`

**Step 1: Initialize dashboard with package.json**

Create `dashboard/package.json`:
```json
{
  "name": "pr-review-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "@supabase/supabase-js": "^2.39.0",
    "recharts": "^2.10.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "typescript": "^5.0.0"
  }
}
```

**Step 2: Create next.config.js**

Create `dashboard/next.config.js`:
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
}

module.exports = nextConfig
```

**Step 3: Create tsconfig.json**

Create `dashboard/tsconfig.json`:
```json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

**Step 4: Create Supabase client**

Create `dashboard/src/lib/supabase.ts`:
```typescript
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseKey)

export interface ReviewEvent {
  id: string
  created_at: string
  repo_owner: string
  repo_name: string
  pr_number: number
  pr_title: string
  pr_author: string
  pr_url: string
  lines_added: number
  lines_removed: number
  files_changed: number
  size_gate_passed: boolean
  lint_gate_passed: boolean
  lint_errors_count: number
  llm_called: boolean
  model_used: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  confidence_score: number
  issues_found: any[]
  outcome: string
  escalated_to_human: boolean
  review_duration_ms: number
}

export interface DailySummary {
  review_date: string
  total_reviews: number
  llm_reviews: number
  gated_reviews: number
  total_cost: number
  avg_confidence: number
  escalations: number
}
```

**Step 5: Create layout**

Create `dashboard/src/app/layout.tsx`:
```tsx
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'PR Review Dashboard',
  description: 'AI PR Review Agent Metrics Dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', backgroundColor: '#f5f5f5' }}>
        {children}
      </body>
    </html>
  )
}
```

**Step 6: Create main dashboard page**

Create `dashboard/src/app/page.tsx`:
```tsx
'use client'

import { useEffect, useState } from 'react'
import { supabase, DailySummary, ReviewEvent } from '@/lib/supabase'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042']

export default function Dashboard() {
  const [dailyStats, setDailyStats] = useState<DailySummary[]>([])
  const [recentReviews, setRecentReviews] = useState<ReviewEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [totalCost, setTotalCost] = useState(0)
  const [totalReviews, setTotalReviews] = useState(0)

  useEffect(() => {
    async function fetchData() {
      // Fetch daily summary
      const { data: daily } = await supabase
        .from('daily_review_summary')
        .select('*')
        .order('review_date', { ascending: false })
        .limit(30)

      if (daily) {
        setDailyStats(daily.reverse())
        setTotalCost(daily.reduce((sum, d) => sum + (d.total_cost || 0), 0))
        setTotalReviews(daily.reduce((sum, d) => sum + d.total_reviews, 0))
      }

      // Fetch recent reviews
      const { data: reviews } = await supabase
        .from('review_events')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(10)

      if (reviews) {
        setRecentReviews(reviews)
      }

      setLoading(false)
    }

    fetchData()
  }, [])

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>Loading...</div>
  }

  // Calculate gate effectiveness
  const gatedCount = dailyStats.reduce((sum, d) => sum + d.gated_reviews, 0)
  const llmCount = dailyStats.reduce((sum, d) => sum + d.llm_reviews, 0)
  const gateData = [
    { name: 'Gated (saved tokens)', value: gatedCount },
    { name: 'LLM Reviews', value: llmCount },
  ]

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ marginBottom: 10 }}>PR Review Dashboard</h1>
      <p style={{ color: '#666', marginBottom: 30 }}>AI-powered code review metrics</p>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 20, marginBottom: 30 }}>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Total Reviews</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>{totalReviews}</div>
        </div>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Total Cost</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>${totalCost.toFixed(2)}</div>
        </div>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Tokens Saved</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>{gatedCount}</div>
          <div style={{ color: '#666', fontSize: 12 }}>reviews gated</div>
        </div>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Avg Confidence</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>
            {dailyStats.length > 0
              ? (dailyStats.reduce((sum, d) => sum + (d.avg_confidence || 0), 0) / dailyStats.length * 100).toFixed(0)
              : 0}%
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20, marginBottom: 30 }}>
        {/* Reviews Over Time */}
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <h3 style={{ marginTop: 0 }}>Reviews Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={dailyStats}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="review_date" tickFormatter={(v) => new Date(v).toLocaleDateString()} />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="total_reviews" stroke="#0088FE" name="Total" />
              <Line type="monotone" dataKey="llm_reviews" stroke="#00C49F" name="LLM" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Gate Effectiveness */}
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <h3 style={{ marginTop: 0 }}>Gate Effectiveness</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={gateData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
              >
                {gateData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cost Over Time */}
      <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: 30 }}>
        <h3 style={{ marginTop: 0 }}>Daily Cost</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={dailyStats}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="review_date" tickFormatter={(v) => new Date(v).toLocaleDateString()} />
            <YAxis tickFormatter={(v) => `$${v.toFixed(2)}`} />
            <Tooltip formatter={(v: number) => `$${v.toFixed(4)}`} />
            <Bar dataKey="total_cost" fill="#8884d8" name="Cost" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Recent Reviews Table */}
      <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <h3 style={{ marginTop: 0 }}>Recent Reviews</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee' }}>
              <th style={{ textAlign: 'left', padding: 10 }}>PR</th>
              <th style={{ textAlign: 'left', padding: 10 }}>Author</th>
              <th style={{ textAlign: 'left', padding: 10 }}>Outcome</th>
              <th style={{ textAlign: 'right', padding: 10 }}>Confidence</th>
              <th style={{ textAlign: 'right', padding: 10 }}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {recentReviews.map((review) => (
              <tr key={review.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: 10 }}>
                  <a href={review.pr_url} target="_blank" rel="noopener noreferrer">
                    {review.repo_name}#{review.pr_number}
                  </a>
                </td>
                <td style={{ padding: 10 }}>{review.pr_author}</td>
                <td style={{ padding: 10 }}>
                  <span style={{
                    background: review.outcome === 'approved' ? '#d4edda' :
                               review.outcome === 'escalated' ? '#f8d7da' : '#fff3cd',
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: 12,
                  }}>
                    {review.outcome || 'gated'}
                  </span>
                </td>
                <td style={{ textAlign: 'right', padding: 10 }}>
                  {review.confidence_score ? `${(review.confidence_score * 100).toFixed(0)}%` : '-'}
                </td>
                <td style={{ textAlign: 'right', padding: 10 }}>
                  {review.cost_usd ? `$${review.cost_usd.toFixed(4)}` : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

**Step 7: Create .env.example**

Create `dashboard/.env.example`:
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

**Step 8: Create .gitignore for dashboard**

Create `dashboard/.gitignore`:
```
node_modules/
.next/
.env
.env.local
```

**Step 9: Commit**

```bash
git add dashboard/
git commit -m "feat: add Next.js metrics dashboard"
```

---

### Task 10: Final verification and documentation

**Step 1: Run all Python tests**

Run:
```bash
uv run pytest -v
```

Expected: All tests PASS

**Step 2: Run linting**

Run:
```bash
uv run ruff check src/ tests/
```

Expected: No errors

**Step 3: Verify CLI help**

Run:
```bash
uv run pr-review-agent --help
```

Expected: Shows help with all options

**Step 4: Final commit**

```bash
git add .
git commit -m "chore: phase 2 & 3 complete"
```

---

## Summary

### Phase 2 Deliverables:
1. **GitHub comment formatter** - Converts review to markdown
2. **post_comment method** - Posts comments via GitHub API
3. **--post-comment flag** - Wired up in CLI
4. **GitHub Action workflow** - Auto-runs on PR events

### Phase 3 Deliverables:
1. **Supabase logger** - Logs all review metrics
2. **SQL schema** - Ready to run in Supabase
3. **Next.js dashboard** with:
   - Summary cards (reviews, cost, tokens saved)
   - Reviews over time chart
   - Gate effectiveness pie chart
   - Daily cost bar chart
   - Recent reviews table

### To deploy:
1. Create Supabase project, run `database/schema.sql`
2. Add secrets to GitHub repo (ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY)
3. Deploy dashboard to Vercel, add env vars
4. Create a test PR to verify end-to-end
