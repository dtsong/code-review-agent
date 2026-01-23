"""GitHub comment formatting and posting."""

from pr_review_agent.review.confidence import ConfidenceResult
from pr_review_agent.review.llm_reviewer import InlineComment, LLMReviewResult


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

    return "\n".join(lines)


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
