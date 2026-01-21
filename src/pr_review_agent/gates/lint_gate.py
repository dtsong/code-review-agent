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
