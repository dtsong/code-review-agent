# Phase 1: Core CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a working CLI that fetches a GitHub PR, runs size and lint gates, and reviews with Claude API.

**Architecture:** Deterministic gates (size, lint) run first to avoid wasting LLM tokens. Only if gates pass does the LLM review execute. Results output to console with structured formatting.

**Tech Stack:** Python 3.12+, uv, anthropic SDK, PyGithub, ruff, pyyaml

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/pr_review_agent/__init__.py`
- Create: `src/pr_review_agent/main.py`
- Create: `.ai-review.yaml`
- Create: `tests/__init__.py`

**Step 1: Initialize uv project**

Run:
```bash
uv init --name pr-review-agent --package
```

Expected: Creates pyproject.toml and basic structure

**Step 2: Restructure for src layout**

Run:
```bash
rm -rf pr_review_agent hello.py
mkdir -p src/pr_review_agent tests
touch src/pr_review_agent/__init__.py tests/__init__.py
```

**Step 3: Update pyproject.toml**

Replace contents with:
```toml
[project]
name = "pr-review-agent"
version = "0.1.0"
description = "AI-powered PR review agent with deterministic gates"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40.0",
    "pygithub>=2.5.0",
    "pyyaml>=6.0",
]

[project.scripts]
pr-review-agent = "pr_review_agent.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pr_review_agent"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.9.0",
]
```

**Step 4: Add dependencies**

Run:
```bash
uv sync
```

Expected: Creates uv.lock, installs dependencies

**Step 5: Create example config file**

Create `.ai-review.yaml`:
```yaml
version: 1

limits:
  max_lines_changed: 500
  max_files_changed: 20

ignore:
  - "*.lock"
  - "*.json"
  - "*.md"
  - "package-lock.json"
  - "pnpm-lock.yaml"
  - "uv.lock"

linting:
  enabled: true
  tool: ruff
  fail_on_error: true
  fail_threshold: 10

llm:
  provider: anthropic
  default_model: claude-sonnet-4-20250514
  simple_model: claude-haiku-4-20250514
  simple_threshold_lines: 50
  max_tokens: 4096

confidence:
  high: 0.8
  low: 0.5

review_focus:
  - logic_errors
  - security_issues
  - missing_tests
  - code_patterns
  - naming_conventions
```

**Step 6: Create minimal main.py**

Create `src/pr_review_agent/main.py`:
```python
"""CLI entrypoint for PR Review Agent."""

import argparse
import sys


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI-powered PR review agent",
        prog="pr-review-agent",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    parser.add_argument("--config", default=".ai-review.yaml", help="Config file path")
    parser.add_argument("--post-comment", action="store_true", help="Post comment to GitHub")

    args = parser.parse_args()
    print(f"Reviewing PR #{args.pr} in {args.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 7: Verify CLI works**

Run:
```bash
uv run pr-review-agent --repo test/repo --pr 1
```

Expected: `Reviewing PR #1 in test/repo`

**Step 8: Commit**

```bash
git init
echo "__pycache__/\n.venv/\n*.egg-info/\n.ruff_cache/" > .gitignore
git add .
git commit -m "feat: initial project scaffold with uv"
```

---

## Task 2: Config Loading

**Files:**
- Create: `src/pr_review_agent/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

Create `tests/test_config.py`:
```python
"""Tests for config loading."""

from pathlib import Path

import pytest

from pr_review_agent.config import Config, load_config


def test_load_config_from_yaml(tmp_path: Path):
    """Test loading config from YAML file."""
    config_file = tmp_path / ".ai-review.yaml"
    config_file.write_text("""
version: 1
limits:
  max_lines_changed: 300
  max_files_changed: 10
linting:
  enabled: true
  fail_threshold: 5
llm:
  default_model: claude-sonnet-4-20250514
""")
    config = load_config(config_file)

    assert config.limits.max_lines_changed == 300
    assert config.limits.max_files_changed == 10
    assert config.linting.enabled is True
    assert config.linting.fail_threshold == 5
    assert config.llm.default_model == "claude-sonnet-4-20250514"


def test_load_config_defaults():
    """Test default config values when file doesn't exist."""
    config = load_config(Path("/nonexistent/.ai-review.yaml"))

    assert config.limits.max_lines_changed == 500
    assert config.limits.max_files_changed == 20
    assert config.linting.enabled is True
    assert config.llm.default_model == "claude-sonnet-4-20250514"


def test_config_ignore_patterns(tmp_path: Path):
    """Test ignore patterns are loaded correctly."""
    config_file = tmp_path / ".ai-review.yaml"
    config_file.write_text("""
version: 1
ignore:
  - "*.lock"
  - "*.md"
""")
    config = load_config(config_file)

    assert "*.lock" in config.ignore
    assert "*.md" in config.ignore
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pr_review_agent.config'`

**Step 3: Write the implementation**

Create `src/pr_review_agent/config.py`:
```python
"""Configuration loading for PR Review Agent."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LimitsConfig:
    """Size limits configuration."""

    max_lines_changed: int = 500
    max_files_changed: int = 20


@dataclass
class LintingConfig:
    """Linting configuration."""

    enabled: bool = True
    tool: str = "ruff"
    fail_on_error: bool = True
    fail_threshold: int = 10


@dataclass
class LLMConfig:
    """LLM configuration."""

    provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-20250514"
    simple_model: str = "claude-haiku-4-20250514"
    simple_threshold_lines: int = 50
    max_tokens: int = 4096


@dataclass
class ConfidenceConfig:
    """Confidence threshold configuration."""

    high: float = 0.8
    low: float = 0.5


@dataclass
class Config:
    """Main configuration object."""

    version: int = 1
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    linting: LintingConfig = field(default_factory=LintingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    ignore: list[str] = field(default_factory=list)
    review_focus: list[str] = field(default_factory=list)


def load_config(path: Path) -> Config:
    """Load configuration from YAML file, with defaults for missing values."""
    config = Config()

    if not path.exists():
        return config

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    if "limits" in data:
        config.limits = LimitsConfig(**data["limits"])

    if "linting" in data:
        config.linting = LintingConfig(**{
            k: v for k, v in data["linting"].items()
            if k in LintingConfig.__dataclass_fields__
        })

    if "llm" in data:
        config.llm = LLMConfig(**{
            k: v for k, v in data["llm"].items()
            if k in LLMConfig.__dataclass_fields__
        })

    if "confidence" in data:
        config.confidence = ConfidenceConfig(**data["confidence"])

    if "ignore" in data:
        config.ignore = data["ignore"]

    if "review_focus" in data:
        config.review_focus = data["review_focus"]

    return config
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_config.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/config.py tests/test_config.py
git commit -m "feat: add config loading from YAML"
```

---

## Task 3: GitHub Client

**Files:**
- Create: `src/pr_review_agent/github_client.py`
- Create: `tests/test_github_client.py`

**Step 1: Write the failing test**

Create `tests/test_github_client.py`:
```python
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_github_client.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/github_client.py`:
```python
"""GitHub client for fetching PR data."""

from dataclasses import dataclass

from github import Github


@dataclass
class PRData:
    """PR data container."""

    owner: str
    repo: str
    number: int
    title: str
    author: str
    description: str
    diff: str
    files_changed: list[str]
    lines_added: int
    lines_removed: int
    base_branch: str
    head_branch: str
    url: str


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(self, token: str):
        """Initialize with GitHub token."""
        self.client = Github(token)

    def fetch_pr(self, owner: str, repo: str, pr_number: int) -> PRData:
        """Fetch all PR data needed for review."""
        repo_obj = self.client.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(pr_number)

        # Get file changes and build diff
        files = list(pr.get_files())
        file_names = [f.filename for f in files]

        # Combine patches into full diff
        diff_parts = []
        for f in files:
            if f.patch:
                diff_parts.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n{f.patch}")

        return PRData(
            owner=owner,
            repo=repo,
            number=pr_number,
            title=pr.title,
            author=pr.user.login,
            description=pr.body or "",
            diff="\n".join(diff_parts),
            files_changed=file_names,
            lines_added=pr.additions,
            lines_removed=pr.deletions,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            url=pr.html_url,
        )
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
git commit -m "feat: add GitHub client for fetching PR data"
```

---

## Task 4: Size Gate

**Files:**
- Create: `src/pr_review_agent/gates/__init__.py`
- Create: `src/pr_review_agent/gates/size_gate.py`
- Create: `tests/test_size_gate.py`

**Step 1: Write the failing test**

Create `tests/test_size_gate.py`:
```python
"""Tests for size gate."""

import pytest

from pr_review_agent.config import Config, LimitsConfig
from pr_review_agent.gates.size_gate import SizeGateResult, check_size
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_size_gate.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/gates/__init__.py`:
```python
"""Gates module for deterministic checks."""

from pr_review_agent.gates.size_gate import SizeGateResult, check_size

__all__ = ["SizeGateResult", "check_size"]
```

Create `src/pr_review_agent/gates/size_gate.py`:
```python
"""Size gate to reject PRs that are too large."""

from dataclasses import dataclass

from pr_review_agent.config import Config
from pr_review_agent.github_client import PRData


@dataclass
class SizeGateResult:
    """Result of size gate check."""

    passed: bool
    reason: str | None
    lines_changed: int
    files_changed: int
    recommendation: str | None


def check_size(pr: PRData, config: Config) -> SizeGateResult:
    """Check if PR size is within acceptable limits."""
    lines_changed = pr.lines_added + pr.lines_removed
    files_changed = len(pr.files_changed)

    max_lines = config.limits.max_lines_changed
    max_files = config.limits.max_files_changed

    if lines_changed > max_lines:
        return SizeGateResult(
            passed=False,
            reason=f"PR has {lines_changed} lines changed (limit: {max_lines})",
            lines_changed=lines_changed,
            files_changed=files_changed,
            recommendation="Consider splitting this PR into smaller, focused changes.",
        )

    if files_changed > max_files:
        return SizeGateResult(
            passed=False,
            reason=f"PR has {files_changed} files changed (limit: {max_files})",
            lines_changed=lines_changed,
            files_changed=files_changed,
            recommendation="Consider splitting this PR into smaller, focused changes.",
        )

    return SizeGateResult(
        passed=True,
        reason=None,
        lines_changed=lines_changed,
        files_changed=files_changed,
        recommendation=None,
    )
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_size_gate.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/gates/ tests/test_size_gate.py
git commit -m "feat: add size gate for PR validation"
```

---

## Task 5: Lint Gate

**Files:**
- Create: `src/pr_review_agent/gates/lint_gate.py`
- Create: `tests/test_lint_gate.py`
- Modify: `src/pr_review_agent/gates/__init__.py`

**Step 1: Write the failing test**

Create `tests/test_lint_gate.py`:
```python
"""Tests for lint gate."""

from pathlib import Path
from unittest.mock import patch

import pytest

from pr_review_agent.config import Config, LintingConfig
from pr_review_agent.gates.lint_gate import LintGateResult, LintIssue, run_lint


def test_lint_gate_passes_clean_files(tmp_path: Path):
    """Clean files should pass lint gate."""
    # Create a clean Python file
    test_file = tmp_path / "clean.py"
    test_file.write_text('def hello():\n    return "world"\n')

    config = Config(linting=LintingConfig(enabled=True, fail_threshold=10))

    result = run_lint([str(test_file)], config)

    assert result.passed is True
    assert result.error_count == 0


def test_lint_gate_disabled():
    """Disabled lint gate should always pass."""
    config = Config(linting=LintingConfig(enabled=False))

    result = run_lint(["nonexistent.py"], config)

    assert result.passed is True
    assert result.issues == []


def test_lint_gate_fails_with_errors(tmp_path: Path):
    """Files with lint errors should fail gate."""
    # Create file with lint errors
    test_file = tmp_path / "bad.py"
    test_file.write_text('import os\nimport sys\nx=1\n')  # unused imports, spacing

    config = Config(linting=LintingConfig(enabled=True, fail_threshold=1))

    result = run_lint([str(test_file)], config)

    assert result.passed is False
    assert result.error_count >= 1
    assert len(result.issues) >= 1


def test_lint_gate_threshold(tmp_path: Path):
    """Gate should pass if errors under threshold."""
    test_file = tmp_path / "minor.py"
    test_file.write_text('import os\nx = 1\n')  # One unused import

    config = Config(linting=LintingConfig(enabled=True, fail_threshold=5))

    result = run_lint([str(test_file)], config)

    # Should pass because errors < threshold
    assert result.passed is True
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_lint_gate.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/gates/lint_gate.py`:
```python
"""Lint gate using Ruff."""

import json
import subprocess
from dataclasses import dataclass, field

from pr_review_agent.config import Config


@dataclass
class LintIssue:
    """Single lint issue."""

    file: str
    line: int
    column: int
    code: str
    message: str


@dataclass
class LintGateResult:
    """Result of lint gate check."""

    passed: bool
    issues: list[LintIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    recommendation: str | None = None


def run_lint(files: list[str], config: Config) -> LintGateResult:
    """Run Ruff on the specified files."""
    if not config.linting.enabled:
        return LintGateResult(passed=True)

    if not files:
        return LintGateResult(passed=True)

    # Filter to only Python files that exist
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return LintGateResult(passed=True)

    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", *py_files],
            capture_output=True,
            text=True,
        )

        issues = []
        if result.stdout:
            try:
                ruff_output = json.loads(result.stdout)
                for item in ruff_output:
                    issues.append(LintIssue(
                        file=item.get("filename", ""),
                        line=item.get("location", {}).get("row", 0),
                        column=item.get("location", {}).get("column", 0),
                        code=item.get("code", ""),
                        message=item.get("message", ""),
                    ))
            except json.JSONDecodeError:
                pass

        error_count = len(issues)
        passed = error_count < config.linting.fail_threshold

        recommendation = None
        if not passed:
            recommendation = f"Fix {error_count} linting errors before AI review."

        return LintGateResult(
            passed=passed,
            issues=issues,
            error_count=error_count,
            warning_count=0,
            recommendation=recommendation,
        )

    except FileNotFoundError:
        # Ruff not installed
        return LintGateResult(
            passed=True,
            recommendation="Ruff not installed, skipping lint check.",
        )
```

Update `src/pr_review_agent/gates/__init__.py`:
```python
"""Gates module for deterministic checks."""

from pr_review_agent.gates.lint_gate import LintGateResult, LintIssue, run_lint
from pr_review_agent.gates.size_gate import SizeGateResult, check_size

__all__ = ["SizeGateResult", "check_size", "LintGateResult", "LintIssue", "run_lint"]
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_lint_gate.py -v
```

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/gates/ tests/test_lint_gate.py
git commit -m "feat: add lint gate using Ruff"
```

---

## Task 6: LLM Reviewer

**Files:**
- Create: `src/pr_review_agent/review/__init__.py`
- Create: `src/pr_review_agent/review/llm_reviewer.py`
- Create: `tests/test_llm_reviewer.py`

**Step 1: Write the failing test**

Create `tests/test_llm_reviewer.py`:
```python
"""Tests for LLM reviewer."""

from unittest.mock import MagicMock, patch

import pytest

from pr_review_agent.config import Config
from pr_review_agent.review.llm_reviewer import LLMReviewResult, LLMReviewer, ReviewIssue


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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_llm_reviewer.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/review/__init__.py`:
```python
"""Review module for LLM-based code review."""

from pr_review_agent.review.llm_reviewer import LLMReviewResult, LLMReviewer, ReviewIssue

__all__ = ["LLMReviewer", "LLMReviewResult", "ReviewIssue"]
```

Create `src/pr_review_agent/review/llm_reviewer.py`:
```python
"""LLM reviewer using Claude API."""

import json
from dataclasses import dataclass, field

from anthropic import Anthropic

from pr_review_agent.config import Config

REVIEW_SYSTEM_PROMPT = """You are an expert code reviewer. Review the PR diff and provide actionable feedback.

Focus on:
1. Logic errors and bugs
2. Security vulnerabilities
3. Missing test coverage
4. Code patterns and best practices
5. Naming and readability

DO NOT focus on (handled by linters):
- Formatting issues
- Import ordering
- Whitespace problems

Respond in JSON format:
{
  "summary": "Brief overall assessment",
  "issues": [
    {
      "severity": "critical|major|minor|suggestion",
      "category": "logic|security|performance|style|testing|documentation",
      "file": "filename",
      "line": null or line number,
      "description": "What's wrong",
      "suggestion": "How to fix it"
    }
  ],
  "strengths": ["What the PR does well"],
  "concerns": ["High-level concerns"],
  "questions": ["Questions for the author"]
}"""


@dataclass
class ReviewIssue:
    """Single review issue."""

    severity: str
    category: str
    file: str
    line: int | None
    description: str
    suggestion: str | None


@dataclass
class LLMReviewResult:
    """Result from LLM review."""

    issues: list[ReviewIssue] = field(default_factory=list)
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0


class LLMReviewer:
    """Claude-based code reviewer."""

    PRICING = {
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-20250514": {"input": 0.00025, "output": 0.00125},
    }

    def __init__(self, api_key: str):
        """Initialize with Anthropic API key."""
        self.client = Anthropic(api_key=api_key)

    def review(
        self,
        diff: str,
        pr_description: str,
        model: str,
        config: Config,
    ) -> LLMReviewResult:
        """Review the PR diff using Claude."""
        user_prompt = f"""## PR Description
{pr_description}

## Diff
```diff
{diff}
```

Please review this PR and provide your feedback in the JSON format specified."""

        response = self.client.messages.create(
            model=model,
            max_tokens=config.llm.max_tokens,
            system=REVIEW_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Parse response
        response_text = response.content[0].text
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response_text[start:end])
            else:
                data = {"summary": response_text, "issues": []}

        issues = [
            ReviewIssue(
                severity=i.get("severity", "minor"),
                category=i.get("category", "style"),
                file=i.get("file", ""),
                line=i.get("line"),
                description=i.get("description", ""),
                suggestion=i.get("suggestion"),
            )
            for i in data.get("issues", [])
        ]

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        return LLMReviewResult(
            issues=issues,
            summary=data.get("summary", ""),
            strengths=data.get("strengths", []),
            concerns=data.get("concerns", []),
            questions=data.get("questions", []),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            cost_usd=cost,
        )

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD."""
        pricing = self.PRICING.get(model, self.PRICING["claude-sonnet-4-20250514"])
        input_cost = (input_tokens * pricing["input"]) / 1000
        output_cost = (output_tokens * pricing["output"]) / 1000
        return input_cost + output_cost
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm_reviewer.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/review/ tests/test_llm_reviewer.py
git commit -m "feat: add LLM reviewer with Claude API"
```

---

## Task 7: Model Selector

**Files:**
- Create: `src/pr_review_agent/review/model_selector.py`
- Create: `tests/test_model_selector.py`
- Modify: `src/pr_review_agent/review/__init__.py`

**Step 1: Write the failing test**

Create `tests/test_model_selector.py`:
```python
"""Tests for model selector."""

import pytest

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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_model_selector.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/review/model_selector.py`:
```python
"""Model selection based on PR characteristics."""

from pr_review_agent.config import Config
from pr_review_agent.github_client import PRData


def select_model(pr: PRData, config: Config) -> str:
    """Select appropriate model based on PR size.

    Small PRs use the cheaper/faster model.
    Larger PRs use the more capable model.
    """
    total_lines = pr.lines_added + pr.lines_removed

    if total_lines < config.llm.simple_threshold_lines:
        return config.llm.simple_model

    return config.llm.default_model
```

Update `src/pr_review_agent/review/__init__.py`:
```python
"""Review module for LLM-based code review."""

from pr_review_agent.review.llm_reviewer import LLMReviewResult, LLMReviewer, ReviewIssue
from pr_review_agent.review.model_selector import select_model

__all__ = ["LLMReviewer", "LLMReviewResult", "ReviewIssue", "select_model"]
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_model_selector.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/review/ tests/test_model_selector.py
git commit -m "feat: add model selector for cost optimization"
```

---

## Task 8: Confidence Scoring

**Files:**
- Create: `src/pr_review_agent/review/confidence.py`
- Create: `tests/test_confidence.py`
- Modify: `src/pr_review_agent/review/__init__.py`

**Step 1: Write the failing test**

Create `tests/test_confidence.py`:
```python
"""Tests for confidence scoring."""

import pytest

from pr_review_agent.config import Config, ConfidenceConfig
from pr_review_agent.github_client import PRData
from pr_review_agent.review.confidence import ConfidenceResult, calculate_confidence
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_confidence.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/review/confidence.py`:
```python
"""Confidence scoring for review results."""

from dataclasses import dataclass, field

from pr_review_agent.config import Config
from pr_review_agent.github_client import PRData
from pr_review_agent.review.llm_reviewer import LLMReviewResult

SEVERITY_WEIGHTS = {
    "critical": 0.4,
    "major": 0.2,
    "minor": 0.05,
    "suggestion": 0.02,
}


@dataclass
class ConfidenceResult:
    """Confidence scoring result."""

    score: float
    level: str
    factors: dict[str, float] = field(default_factory=dict)
    recommendation: str = ""


def calculate_confidence(
    review: LLMReviewResult,
    pr: PRData,
    config: Config,
) -> ConfidenceResult:
    """Calculate confidence score based on review results."""
    # Start with base score
    score = 1.0
    factors = {}

    # Deduct for issues by severity
    issue_penalty = 0.0
    for issue in review.issues:
        penalty = SEVERITY_WEIGHTS.get(issue.severity, 0.05)
        issue_penalty += penalty

    score -= issue_penalty
    factors["issues"] = -issue_penalty

    # Bonus for having strengths mentioned
    if review.strengths:
        strength_bonus = min(0.1, len(review.strengths) * 0.03)
        score += strength_bonus
        factors["strengths"] = strength_bonus

    # Penalty for concerns
    if review.concerns:
        concern_penalty = min(0.2, len(review.concerns) * 0.05)
        score -= concern_penalty
        factors["concerns"] = -concern_penalty

    # Penalty for questions (uncertainty)
    if review.questions:
        question_penalty = min(0.15, len(review.questions) * 0.05)
        score -= question_penalty
        factors["questions"] = -question_penalty

    # Clamp to valid range
    score = max(0.0, min(1.0, score))

    # Determine level and recommendation
    high_threshold = config.confidence.high
    low_threshold = config.confidence.low

    if score >= high_threshold:
        level = "high"
        recommendation = "auto_approve"
    elif score >= low_threshold:
        level = "medium"
        recommendation = "comment_only"
    else:
        level = "low"
        recommendation = "request_human_review"

    return ConfidenceResult(
        score=score,
        level=level,
        factors=factors,
        recommendation=recommendation,
    )
```

Update `src/pr_review_agent/review/__init__.py`:
```python
"""Review module for LLM-based code review."""

from pr_review_agent.review.confidence import ConfidenceResult, calculate_confidence
from pr_review_agent.review.llm_reviewer import LLMReviewResult, LLMReviewer, ReviewIssue
from pr_review_agent.review.model_selector import select_model

__all__ = [
    "LLMReviewer",
    "LLMReviewResult",
    "ReviewIssue",
    "select_model",
    "ConfidenceResult",
    "calculate_confidence",
]
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_confidence.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/review/ tests/test_confidence.py
git commit -m "feat: add confidence scoring for review results"
```

---

## Task 9: Console Output

**Files:**
- Create: `src/pr_review_agent/output/__init__.py`
- Create: `src/pr_review_agent/output/console.py`
- Create: `tests/test_console_output.py`

**Step 1: Write the failing test**

Create `tests/test_console_output.py`:
```python
"""Tests for console output."""

import pytest

from pr_review_agent.gates.lint_gate import LintGateResult, LintIssue
from pr_review_agent.gates.size_gate import SizeGateResult
from pr_review_agent.github_client import PRData
from pr_review_agent.output.console import format_review_output
from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import LLMReviewResult, ReviewIssue


def make_pr() -> PRData:
    """Create test PR."""
    return PRData(
        owner="test",
        repo="repo",
        number=1,
        title="Test PR",
        author="user",
        description="",
        diff="",
        files_changed=["file.py"],
        lines_added=50,
        lines_removed=10,
        base_branch="main",
        head_branch="feature",
        url="https://github.com/test/repo/pull/1",
    )


def test_format_output_gated_by_size():
    """Output should show size gate failure."""
    output = format_review_output(
        pr=make_pr(),
        size_result=SizeGateResult(
            passed=False,
            reason="Too large",
            lines_changed=1000,
            files_changed=50,
            recommendation="Split the PR",
        ),
        lint_result=None,
        review_result=None,
        confidence=None,
    )

    assert "Size Gate" in output
    assert "FAILED" in output
    assert "Too large" in output


def test_format_output_with_review():
    """Output should show full review results."""
    output = format_review_output(
        pr=make_pr(),
        size_result=SizeGateResult(
            passed=True, reason=None, lines_changed=60, files_changed=1, recommendation=None
        ),
        lint_result=LintGateResult(passed=True),
        review_result=LLMReviewResult(
            summary="Good PR overall",
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
            strengths=["Clean code"],
            input_tokens=100,
            output_tokens=50,
            model="claude-sonnet-4-20250514",
            cost_usd=0.001,
        ),
        confidence=ConfidenceResult(
            score=0.85,
            level="high",
            recommendation="auto_approve",
        ),
    )

    assert "Good PR overall" in output
    assert "minor" in output.lower()
    assert "Confidence" in output
    assert "0.85" in output
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_console_output.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/pr_review_agent/output/__init__.py`:
```python
"""Output module for formatting results."""

from pr_review_agent.output.console import format_review_output, print_results

__all__ = ["format_review_output", "print_results"]
```

Create `src/pr_review_agent/output/console.py`:
```python
"""Console output formatting."""

from pr_review_agent.gates.lint_gate import LintGateResult
from pr_review_agent.gates.size_gate import SizeGateResult
from pr_review_agent.github_client import PRData
from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import LLMReviewResult


def format_review_output(
    pr: PRData,
    size_result: SizeGateResult,
    lint_result: LintGateResult | None,
    review_result: LLMReviewResult | None,
    confidence: ConfidenceResult | None,
) -> str:
    """Format complete review output for console."""
    lines = []

    # Header
    lines.append("=" * 60)
    lines.append(f"PR Review: {pr.title}")
    lines.append(f"Repository: {pr.owner}/{pr.repo} #{pr.number}")
    lines.append(f"Author: {pr.author}")
    lines.append(f"URL: {pr.url}")
    lines.append("=" * 60)
    lines.append("")

    # Size Gate
    lines.append("## Size Gate")
    if size_result.passed:
        lines.append(f"✓ PASSED ({size_result.lines_changed} lines, {size_result.files_changed} files)")
    else:
        lines.append(f"✗ FAILED: {size_result.reason}")
        if size_result.recommendation:
            lines.append(f"  Recommendation: {size_result.recommendation}")
        lines.append("")
        lines.append("Review stopped - PR too large for automated review.")
        return "\n".join(lines)

    lines.append("")

    # Lint Gate
    lines.append("## Lint Gate")
    if lint_result is None:
        lines.append("⊘ SKIPPED")
    elif lint_result.passed:
        lines.append(f"✓ PASSED ({lint_result.error_count} issues)")
    else:
        lines.append(f"✗ FAILED: {lint_result.error_count} linting errors")
        if lint_result.recommendation:
            lines.append(f"  Recommendation: {lint_result.recommendation}")
        for issue in lint_result.issues[:5]:  # Show first 5
            lines.append(f"  - {issue.file}:{issue.line} [{issue.code}] {issue.message}")
        if len(lint_result.issues) > 5:
            lines.append(f"  ... and {len(lint_result.issues) - 5} more")
        lines.append("")
        lines.append("Review stopped - fix linting errors first.")
        return "\n".join(lines)

    lines.append("")

    # LLM Review
    if review_result:
        lines.append("## AI Review")
        lines.append(f"Model: {review_result.model}")
        lines.append(f"Tokens: {review_result.input_tokens} in / {review_result.output_tokens} out")
        lines.append(f"Cost: ${review_result.cost_usd:.4f}")
        lines.append("")

        lines.append("### Summary")
        lines.append(review_result.summary)
        lines.append("")

        if review_result.strengths:
            lines.append("### Strengths")
            for s in review_result.strengths:
                lines.append(f"  ✓ {s}")
            lines.append("")

        if review_result.issues:
            lines.append("### Issues")
            for issue in review_result.issues:
                severity_icon = {"critical": "🔴", "major": "🟠", "minor": "🟡", "suggestion": "💡"}.get(issue.severity, "•")
                loc = f"{issue.file}:{issue.line}" if issue.line else issue.file
                lines.append(f"  {severity_icon} [{issue.severity.upper()}] {loc}")
                lines.append(f"     {issue.description}")
                if issue.suggestion:
                    lines.append(f"     → {issue.suggestion}")
            lines.append("")

        if review_result.concerns:
            lines.append("### Concerns")
            for c in review_result.concerns:
                lines.append(f"  ⚠ {c}")
            lines.append("")

        if review_result.questions:
            lines.append("### Questions for Author")
            for q in review_result.questions:
                lines.append(f"  ? {q}")
            lines.append("")

    # Confidence
    if confidence:
        lines.append("## Confidence")
        level_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence.level, "•")
        lines.append(f"{level_icon} Score: {confidence.score:.2f} ({confidence.level.upper()})")
        lines.append(f"Recommendation: {confidence.recommendation}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def print_results(
    pr: PRData,
    size_result: SizeGateResult,
    lint_result: LintGateResult | None,
    review_result: LLMReviewResult | None,
    confidence: ConfidenceResult | None,
) -> None:
    """Print formatted review results to console."""
    output = format_review_output(pr, size_result, lint_result, review_result, confidence)
    print(output)
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_console_output.py -v
```

Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/pr_review_agent/output/ tests/test_console_output.py
git commit -m "feat: add console output formatting"
```

---

## Task 10: Wire Up Main CLI

**Files:**
- Modify: `src/pr_review_agent/main.py`
- Create: `tests/test_main.py`

**Step 1: Write the integration test**

Create `tests/test_main.py`:
```python
"""Integration tests for main CLI."""

from unittest.mock import MagicMock, patch

import pytest

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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_main.py -v
```

Expected: FAIL (run_review doesn't exist yet)

**Step 3: Write the full main.py implementation**

Replace `src/pr_review_agent/main.py`:
```python
"""CLI entrypoint for PR Review Agent."""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from pr_review_agent.config import load_config
from pr_review_agent.gates.lint_gate import run_lint
from pr_review_agent.gates.size_gate import check_size
from pr_review_agent.github_client import GitHubClient
from pr_review_agent.output.console import print_results
from pr_review_agent.review.confidence import calculate_confidence
from pr_review_agent.review.llm_reviewer import LLMReviewer
from pr_review_agent.review.model_selector import select_model


def run_review(
    repo: str,
    pr_number: int,
    github_token: str,
    anthropic_key: str,
    config_path: Path | None,
) -> dict[str, Any]:
    """Run the full PR review pipeline.

    Returns dict with results for metrics logging.
    """
    start_time = time.time()

    # Load config
    config = load_config(config_path or Path(".ai-review.yaml"))

    # Initialize clients
    github = GitHubClient(github_token)

    # Fetch PR data
    owner, repo_name = repo.split("/")
    pr = github.fetch_pr(owner, repo_name, pr_number)

    # Initialize result tracking
    result: dict[str, Any] = {
        "pr_number": pr_number,
        "repo": repo,
        "size_gate_passed": False,
        "lint_gate_passed": False,
        "llm_called": False,
        "confidence_score": 0.0,
    }

    # Gate 1: Size check
    size_result = check_size(pr, config)
    result["size_gate_passed"] = size_result.passed

    if not size_result.passed:
        print_results(pr, size_result, None, None, None)
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        return result

    # Gate 2: Lint check
    # Filter files based on ignore patterns
    files_to_lint = [
        f for f in pr.files_changed
        if not any(_match_pattern(f, p) for p in config.ignore)
    ]
    lint_result = run_lint(files_to_lint, config)
    result["lint_gate_passed"] = lint_result.passed

    if not lint_result.passed:
        print_results(pr, size_result, lint_result, None, None)
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        return result

    # All gates passed - run LLM review
    llm_reviewer = LLMReviewer(anthropic_key)
    model = select_model(pr, config)
    review_result = llm_reviewer.review(
        diff=pr.diff,
        pr_description=pr.description,
        model=model,
        config=config,
    )
    result["llm_called"] = True

    # Calculate confidence
    confidence = calculate_confidence(review_result, pr, config)
    result["confidence_score"] = confidence.score

    # Output results
    print_results(pr, size_result, lint_result, review_result, confidence)

    result["duration_ms"] = int((time.time() - start_time) * 1000)
    return result


def _match_pattern(filename: str, pattern: str) -> bool:
    """Simple glob pattern matching."""
    import fnmatch
    return fnmatch.fnmatch(filename, pattern)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI-powered PR review agent",
        prog="pr-review-agent",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    parser.add_argument("--config", default=".ai-review.yaml", help="Config file path")
    parser.add_argument("--post-comment", action="store_true", help="Post comment to GitHub")

    args = parser.parse_args()

    # Get credentials from environment
    github_token = os.environ.get("GITHUB_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable required", file=sys.stderr)
        return 1

    if not anthropic_key:
        print("Error: ANTHROPIC_API_KEY environment variable required", file=sys.stderr)
        return 1

    try:
        run_review(
            repo=args.repo,
            pr_number=args.pr,
            github_token=github_token,
            anthropic_key=anthropic_key,
            config_path=Path(args.config) if args.config else None,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_main.py -v
```

Expected: All 2 tests PASS

**Step 5: Run all tests**

Run:
```bash
uv run pytest -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/pr_review_agent/main.py tests/test_main.py
git commit -m "feat: wire up complete CLI with all components"
```

---

## Task 11: Final Verification

**Step 1: Run linting on own code**

Run:
```bash
uv run ruff check src/ tests/
```

Expected: No errors (or fix any that appear)

**Step 2: Run full test suite**

Run:
```bash
uv run pytest -v --tb=short
```

Expected: All tests pass

**Step 3: Test CLI help**

Run:
```bash
uv run pr-review-agent --help
```

Expected: Shows help with all options

**Step 4: Final commit**

```bash
git add .
git commit -m "chore: phase 1 complete - core CLI ready"
```

---

## Summary

Phase 1 delivers:

1. **Project scaffold** with uv, proper src layout, dependencies
2. **Config loading** from `.ai-review.yaml` with sensible defaults
3. **GitHub client** to fetch PR data via PyGithub
4. **Size gate** to reject large PRs (saves LLM costs)
5. **Lint gate** to reject PRs with Ruff errors (saves LLM costs)
6. **LLM reviewer** calling Claude API directly
7. **Model selector** for cost optimization (Haiku vs Sonnet)
8. **Confidence scoring** for review results
9. **Console output** with formatted results
10. **Wired up CLI** connecting all components

To test against a real PR:
```bash
export GITHUB_TOKEN=your_token
export ANTHROPIC_API_KEY=your_key
uv run pr-review-agent --repo owner/repo --pr 123
```
