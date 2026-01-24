"""Tests for console output."""

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


def test_format_output_lint_skipped():
    """Lint gate shows SKIPPED when lint_result is None."""
    output = format_review_output(
        pr=make_pr(),
        size_result=SizeGateResult(
            passed=True, reason=None, lines_changed=60, files_changed=1, recommendation=None
        ),
        lint_result=None,
        review_result=None,
        confidence=None,
    )

    assert "SKIPPED" in output


def test_format_output_lint_failed_with_issues():
    """Lint gate failure shows error details and issues."""
    output = format_review_output(
        pr=make_pr(),
        size_result=SizeGateResult(
            passed=True, reason=None, lines_changed=60, files_changed=1, recommendation=None
        ),
        lint_result=LintGateResult(
            passed=False,
            error_count=3,
            issues=[
                LintIssue(file="a.py", line=10, column=1, code="E501", message="Line too long"),
                LintIssue(file="b.py", line=5, column=3, code="F401", message="Unused import"),
            ],
            recommendation="Run ruff --fix",
        ),
        review_result=None,
        confidence=None,
    )

    assert "FAILED" in output
    assert "3 linting errors" in output
    assert "E501" in output
    assert "Run ruff --fix" in output
    assert "fix linting errors" in output


def test_format_output_with_concerns():
    """Concerns section rendered when present."""
    output = format_review_output(
        pr=make_pr(),
        size_result=SizeGateResult(
            passed=True, reason=None, lines_changed=60, files_changed=1, recommendation=None
        ),
        lint_result=LintGateResult(passed=True),
        review_result=LLMReviewResult(
            summary="Mostly fine",
            issues=[],
            concerns=["Performance may degrade under load", "Missing error handling"],
            input_tokens=100,
            output_tokens=50,
            model="claude-sonnet-4-20250514",
            cost_usd=0.001,
        ),
        confidence=None,
    )

    assert "Concerns" in output
    assert "Performance may degrade" in output
    assert "Missing error handling" in output


def test_format_output_with_questions():
    """Questions section rendered when present."""
    output = format_review_output(
        pr=make_pr(),
        size_result=SizeGateResult(
            passed=True, reason=None, lines_changed=60, files_changed=1, recommendation=None
        ),
        lint_result=LintGateResult(passed=True),
        review_result=LLMReviewResult(
            summary="Needs clarification",
            issues=[],
            questions=["Why was this approach chosen?", "Is this backwards compatible?"],
            input_tokens=100,
            output_tokens=50,
            model="claude-sonnet-4-20250514",
            cost_usd=0.001,
        ),
        confidence=None,
    )

    assert "Questions for Author" in output
    assert "Why was this approach chosen?" in output
    assert "Is this backwards compatible?" in output
