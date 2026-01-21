"""LLM reviewer using Claude API."""

import json
from dataclasses import dataclass, field

from anthropic import Anthropic

from pr_review_agent.config import Config

REVIEW_SYSTEM_PROMPT = """\
You are an expert code reviewer. Review the PR diff and provide actionable feedback.

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
