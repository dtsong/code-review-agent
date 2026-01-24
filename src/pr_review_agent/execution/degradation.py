"""Graceful degradation for LLM review failures.

Implements a cascading fallback strategy:
  Full (with retries) → Reduced/Haiku (with retries) → Gates-only → Minimal

Always produces some output, never fails silently.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pr_review_agent.execution.retry_handler import RetryStrategy, retry_with_adaptation
from pr_review_agent.review.llm_reviewer import LLMReviewer, LLMReviewResult


class DegradationLevel(Enum):
    """Degradation levels from best to worst."""

    FULL = "full"
    REDUCED = "reduced"
    GATES_ONLY = "gates_only"
    MINIMAL = "minimal"


@dataclass
class DegradationResult:
    """Result from the degraded pipeline."""

    level: DegradationLevel
    review_result: LLMReviewResult | None
    gate_results: dict[str, Any]
    error_message: str | None = None
    errors: list[str] = field(default_factory=list)


class DegradedReviewPipeline:
    """Review pipeline with graceful degradation on failure.

    Cascades through degradation levels:
    1. Full - primary model review (with retry/backoff)
    2. Reduced - Haiku fallback (with retry/backoff)
    3. Gates-only - only deterministic gate results
    4. Minimal - error notice
    """

    def __init__(
        self,
        anthropic_key: str,
        diff: str,
        pr_description: str,
        config: Any,
        focus_areas: list[str] | None = None,
        base_model: str = "claude-sonnet-4-20250514",
        gate_results: dict[str, Any] | None = None,
    ):
        self._reviewer = LLMReviewer(anthropic_key)
        self.diff = diff
        self.pr_description = pr_description
        self.config = config
        self.focus_areas = focus_areas or []
        self.base_model = base_model
        self._gate_results = gate_results or {}
        self._errors: list[str] = []

    def execute(self) -> DegradationResult:
        """Execute the review pipeline with graceful degradation.

        Always returns a result, never raises exceptions.
        """
        # Try full review with retry/backoff
        try:
            review = self._run_full_review()
            return DegradationResult(
                level=DegradationLevel.FULL,
                review_result=review,
                gate_results=self._gate_results,
                errors=self._errors,
            )
        except Exception as e:
            self._errors.append(f"Full review failed: {e}")

        # Try reduced review with retry/backoff (Haiku fallback)
        try:
            review = self._run_reduced_review()
            return DegradationResult(
                level=DegradationLevel.REDUCED,
                review_result=review,
                gate_results=self._gate_results,
                errors=self._errors,
            )
        except Exception as e:
            self._errors.append(f"Reduced review failed: {e}")

        # Fall back to gates-only
        return DegradationResult(
            level=DegradationLevel.GATES_ONLY,
            review_result=None,
            gate_results=self._gate_results,
            error_message="LLM review unavailable; showing gate results only",
            errors=self._errors,
        )

    def _run_full_review(self) -> LLMReviewResult:
        """Run full LLM review with retries and strategy adaptation."""
        def do_review(strategy: RetryStrategy) -> LLMReviewResult:
            return self._reviewer.review(
                diff=self.diff,
                pr_description=self.pr_description,
                model=strategy.model,
                config=self.config,
                focus_areas=self.focus_areas,
            )

        def validate(result: LLMReviewResult) -> bool:
            return result is not None and len(result.summary) > 20

        return retry_with_adaptation(
            operation=do_review,
            base_model=self.base_model,
            max_attempts=3,
            validator=validate,
        )

    def _run_reduced_review(self) -> LLMReviewResult:
        """Run reduced review using Haiku with retries."""
        fallback_model = self.config.llm.simple_model

        def do_review(strategy: RetryStrategy) -> LLMReviewResult:
            return self._reviewer.review(
                diff=self.diff,
                pr_description=self.pr_description,
                model=strategy.model,
                config=self.config,
                focus_areas=self.focus_areas,
            )

        def validate(result: LLMReviewResult) -> bool:
            return result is not None and len(result.summary) > 20

        return retry_with_adaptation(
            operation=do_review,
            base_model=fallback_model,
            max_attempts=2,
            validator=validate,
        )
