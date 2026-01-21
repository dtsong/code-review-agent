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
        size_info = f"{size_result.lines_changed} lines, {size_result.files_changed} files"
        lines.append(f"✓ PASSED ({size_info})")
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
            severity_icons = {
                "critical": "🔴",
                "major": "🟠",
                "minor": "🟡",
                "suggestion": "💡",
            }
            for issue in review_result.issues:
                severity_icon = severity_icons.get(issue.severity, "•")
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
