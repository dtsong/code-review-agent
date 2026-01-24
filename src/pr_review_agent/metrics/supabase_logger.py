"""Supabase metrics logger."""

from supabase import Client, create_client

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
                        "fingerprint": i.fingerprint,
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
