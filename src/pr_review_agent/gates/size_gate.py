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
