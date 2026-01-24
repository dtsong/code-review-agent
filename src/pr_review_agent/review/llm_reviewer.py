"""LLM reviewer using Claude API."""

import json
from dataclasses import dataclass, field

from anthropic import Anthropic

from pr_review_agent.config import Config
from pr_review_agent.metrics.token_tracker import calculate_cost
from pr_review_agent.review.fingerprint import fingerprint_issue
from pr_review_agent.review.sanitizer import sanitize_diff

REVIEW_SYSTEM_PROMPT = """\
You are an expert code reviewer. Review the PR diff and provide actionable feedback.

{focus_instruction}

DO NOT focus on (handled by linters):
- Formatting issues
- Import ordering
- Whitespace problems

For each issue, provide the exact file path and line number(s) from the diff.
Use start_line and end_line for multi-line issues.

## Code Suggestions

For critical and major issues where you are confident in the fix, provide a \
concrete code fix in the "code_suggestion" field. This will be rendered as a \
GitHub suggestion block that the author can apply with one click.

Rules for code_suggestion:
- ONLY provide for critical or major severity issues
- ONLY provide when you are highly confident the fix is correct
- The code_suggestion must be the EXACT replacement text for the lines from \
start_line to end_line (inclusive)
- Preserve the original indentation and style
- Do NOT include the code_suggestion field for minor issues or suggestions
- If the fix spans a single line, set start_line and end_line to the same value

Example: if start_line=10, end_line=12, and the original code is:
  x = get_data()
  result = process(x)
  return result

A valid code_suggestion replacing those 3 lines would be:
  "code_suggestion": "  x = get_data()\\n  if x is None:\\n    return None\\n  return process(x)"

Respond in JSON format:
{{
  "summary": "Brief overall assessment",
  "issues": [
    {{
      "severity": "critical|major|minor|suggestion",
      "category": "logic|security|performance|style|testing|documentation",
      "file": "path/to/file.py",
      "start_line": 42,
      "end_line": 42,
      "description": "What's wrong",
      "suggestion": "How to fix it (text explanation)",
      "code_suggestion": "replacement code here (only for critical/major)"
    }}
  ],
  "strengths": ["What the PR does well"],
  "concerns": ["High-level concerns"],
  "questions": ["Questions for the author"]
}}"""


DEFAULT_FOCUS_AREAS = [
    "logic_correctness",
    "edge_cases",
    "security_issues",
    "test_coverage",
    "code_quality",
]


def _build_focus_instruction(focus_areas: list[str] | None) -> str:
    """Build focus instruction based on provided areas."""
    if not focus_areas:
        focus_areas = DEFAULT_FOCUS_AREAS

    focus_map = {
        "logic_correctness": "Logic errors and bugs",
        "edge_cases": "Edge cases and boundary conditions",
        "security_issues": "Security vulnerabilities",
        "security_implications": "Security implications of the changes",
        "test_coverage": "Missing test coverage",
        "code_quality": "Code patterns and best practices",
        "root_cause": "Root cause analysis for bug fixes",
        "regression_risk": "Potential regression risks",
        "behavior_preservation": "Behavior preservation during refactoring",
        "performance": "Performance implications",
        "vulnerabilities": "Security vulnerabilities and attack vectors",
        "auth_logic": "Authentication and authorization logic",
        "input_validation": "Input validation and sanitization",
        "secrets": "Exposure of secrets or credentials",
        "coverage_gaps": "Test coverage gaps",
        "test_quality": "Test quality and assertions",
        "assertions": "Proper test assertions",
        "accuracy": "Documentation accuracy",
        "completeness": "Documentation completeness",
        "clarity": "Documentation clarity",
        "breaking_changes": "Breaking changes in dependencies",
        "security_advisories": "Security advisories in dependencies",
        "compatibility": "Backward compatibility",
        "environment_consistency": "Environment consistency",
    }

    focus_items = [focus_map.get(area, area) for area in focus_areas]
    numbered_focus = "\n".join(f"{i+1}. {item}" for i, item in enumerate(focus_items))

    return f"Focus on:\n{numbered_focus}"


@dataclass
class ReviewIssue:
    """Single review issue."""

    severity: str
    category: str
    file: str
    line: int | None
    description: str
    suggestion: str | None
    start_line: int | None = None
    end_line: int | None = None
    code_suggestion: str | None = None
    fingerprint: str | None = None


@dataclass
class InlineComment:
    """Line-specific comment for GitHub Review API."""

    file: str
    start_line: int
    end_line: int | None
    body: str
    suggestion: str | None  # Code suggestion in diff format


@dataclass
class LLMReviewResult:
    """Result from LLM review."""

    issues: list[ReviewIssue] = field(default_factory=list)
    inline_comments: list[InlineComment] = field(default_factory=list)
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

    def __init__(self, api_key: str):
        """Initialize with Anthropic API key."""
        self.client = Anthropic(api_key=api_key)

    def review(
        self,
        diff: str,
        pr_description: str,
        model: str,
        config: Config,
        focus_areas: list[str] | None = None,
    ) -> LLMReviewResult:
        """Review the PR diff using Claude."""
        # Sanitize diff to neutralize prompt injection attempts
        sanitization = sanitize_diff(diff)
        if not sanitization.is_clean:
            patterns = [a.pattern_type for a in sanitization.attempts_detected]
            print(f"   ⚠ Injection attempts detected and sanitized: {patterns}")
        safe_diff = sanitization.sanitized_diff

        user_prompt = f"""## PR Description
{pr_description}

## Diff
```diff
{safe_diff}
```

Please review this PR and provide your feedback in the JSON format specified."""

        # Build system prompt with focus areas
        focus_instruction = _build_focus_instruction(focus_areas)
        system_prompt = REVIEW_SYSTEM_PROMPT.format(focus_instruction=focus_instruction)

        response = self.client.messages.create(
            model=model,
            max_tokens=config.llm.max_tokens,
            system=system_prompt,
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

        issues = []
        inline_comments = []

        for i in data.get("issues", []):
            start_line = i.get("start_line") or i.get("line")
            end_line = i.get("end_line")
            code_suggestion = i.get("code_suggestion")

            issue = ReviewIssue(
                severity=i.get("severity", "minor"),
                category=i.get("category", "style"),
                file=i.get("file", ""),
                line=start_line,
                description=i.get("description", ""),
                suggestion=i.get("suggestion"),
                start_line=start_line,
                end_line=end_line,
                code_suggestion=code_suggestion,
            )
            issue.fingerprint = fingerprint_issue(issue)
            issues.append(issue)

            # Build inline comment if we have file + line info
            if issue.file and start_line:
                body = f"**{issue.severity.upper()}** ({issue.category}): "
                body += issue.description
                if issue.suggestion:
                    body += f"\n\n*Suggestion: {issue.suggestion}*"

                # Only include code suggestions for high-confidence issues
                filtered_suggestion = (
                    code_suggestion
                    if issue.severity in ("critical", "major")
                    else None
                )

                inline_comments.append(InlineComment(
                    file=issue.file,
                    start_line=start_line,
                    end_line=end_line,
                    body=body,
                    suggestion=filtered_suggestion,
                ))

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = calculate_cost(model, input_tokens, output_tokens)

        return LLMReviewResult(
            issues=issues,
            inline_comments=inline_comments,
            summary=data.get("summary", ""),
            strengths=data.get("strengths", []),
            concerns=data.get("concerns", []),
            questions=data.get("questions", []),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            cost_usd=cost,
        )
