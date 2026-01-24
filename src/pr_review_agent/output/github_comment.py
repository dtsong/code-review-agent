"""GitHub comment formatting and posting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pr_review_agent.output.secret_scanner import redact_secrets
from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import InlineComment, LLMReviewResult

if TYPE_CHECKING:
    from pr_review_agent.execution.degradation import DegradationResult


def format_as_markdown(
    review: LLMReviewResult,
    confidence: ConfidenceResult,
) -> str:
    """Format review results as GitHub-flavored markdown."""
    lines = []

    # Header
    lines.append("## AI Code Review")
    lines.append("")

    # Summary
    lines.append("### Summary")
    lines.append(review.summary)
    lines.append("")

    # Confidence
    lines.append(f"**Confidence:** {confidence.score:.2f} ({confidence.level})")
    if confidence.level == "low":
        lines.append("*This PR may require human review*")
    lines.append("")

    # Strengths
    if review.strengths:
        lines.append("### Strengths")
        for strength in review.strengths:
            lines.append(f"- {strength}")
        lines.append("")

    # Issues
    if review.issues:
        lines.append("### Issues Found")
        lines.append("")

        # Group by severity
        severity_order = ["critical", "major", "minor", "suggestion"]

        for severity in severity_order:
            severity_issues = [i for i in review.issues if i.severity == severity]
            if severity_issues:
                lines.append(f"#### {severity.title()} ({len(severity_issues)})")
                lines.append("")
                for issue in severity_issues:
                    location = f"`{issue.file}:{issue.line}`" if issue.line else f"`{issue.file}`"
                    lines.append(f"**{location}** - {issue.category}")
                    lines.append(f"> {issue.description}")
                    if issue.suggestion:
                        lines.append(f"> *Suggestion: {issue.suggestion}*")
                    lines.append("")
    else:
        lines.append("### No issues found")
        lines.append("")

    # Concerns
    if review.concerns:
        lines.append("### Concerns")
        for concern in review.concerns:
            lines.append(f"- {concern}")
        lines.append("")

    # Questions
    if review.questions:
        lines.append("### Questions")
        for question in review.questions:
            lines.append(f"- {question}")
        lines.append("")

    # Footer with metadata
    lines.append("---")
    lines.append(f"<sub>Model: `{review.model}` | Cost: ${review.cost_usd:.4f} | ")
    lines.append(f"Tokens: {review.input_tokens} in / {review.output_tokens} out</sub>")

    output = "\n".join(lines)

    # Scan and redact any accidentally exposed secrets
    result = redact_secrets(output)
    if result.secrets_found > 0:
        print(f"   ⚠ Redacted {result.secrets_found} secret(s) from review output")
    return result.redacted_text


def build_review_comments(
    inline_comments: list[InlineComment],
) -> list[dict]:
    """Convert InlineComment objects to GitHub Review API comment format.

    Returns list of dicts with keys: path, line, body, start_line (optional).
    """
    comments = []
    for ic in inline_comments:
        body = ic.body
        # Add code suggestion block if present
        if ic.suggestion:
            body += f"\n\n```suggestion\n{ic.suggestion}\n```"

        comment: dict = {
            "path": ic.file,
            "line": ic.end_line or ic.start_line,
            "body": body,
        }
        if ic.end_line and ic.start_line != ic.end_line:
            comment["start_line"] = ic.start_line

        comments.append(comment)

    return comments


_LEVEL_LABELS = {
    "full": "Full Review",
    "reduced": "Reduced Review (Fallback Model)",
    "gates_only": "Gates Only (LLM Unavailable)",
    "minimal": "Minimal (Infrastructure Error)",
}


def format_degraded_review(result: DegradationResult) -> str:
    """Format a degraded review result as GitHub-flavored markdown.

    Used when LLM review is unavailable (gates-only or minimal).
    Full/reduced reviews with a review_result use format_as_markdown instead.
    """
    from pr_review_agent.execution.degradation import DegradationLevel

    lines = []
    level_label = _LEVEL_LABELS.get(result.level.value, result.level.value)

    if result.level == DegradationLevel.GATES_ONLY:
        # Gates-only - show what deterministic checks found
        lines.append("## AI Code Review - Gates Only")
        lines.append("")
        lines.append(f"> **{level_label}**")
        if result.error_message:
            lines.append(f"> {result.error_message}")
        lines.append("")

        if result.gate_results:
            lines.append("### Gate Results")
            for gate_name, gate_result in result.gate_results.items():
                status = "PASS" if getattr(gate_result, "passed", False) else "FAIL"
                lines.append(f"- **{gate_name}**: {status}")
            lines.append("")

        if result.errors:
            lines.append("### Errors")
            for error in result.errors:
                lines.append(f"- {error}")
            lines.append("")

        lines.append("---")
        lines.append("<sub>LLM review was unavailable. Only deterministic gates ran.</sub>")

    else:
        # Minimal - just show error
        lines.append("## AI Code Review - Service Unavailable")
        lines.append("")
        lines.append(f"> **{level_label}**")
        if result.error_message:
            lines.append(f"> {result.error_message}")
        lines.append("")
        lines.append("The review service encountered an infrastructure issue. ")
        lines.append("Please retry or request a manual review.")
        lines.append("")

        if result.errors:
            lines.append("### Errors")
            for error in result.errors:
                lines.append(f"- {error}")
            lines.append("")

        lines.append("---")
        lines.append("<sub>No review data available.</sub>")

    return "\n".join(lines)
