"""Graceful degradation for LLM review failures.

Implements a cascading fallback strategy:
  Full → Reduced (Haiku) → Gates-only → Minimal

Always produces some output, never fails silently.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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
    1. Full - primary model review
    2. Reduced - Haiku fallback
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
        self.anthropic_key = anthropic_key
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
        # Try full review first
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

        # Try reduced review (Haiku fallback)
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
        try:
            gate_results = self._collect_gate_results()
            return DegradationResult(
                level=DegradationLevel.GATES_ONLY,
                review_result=None,
                gate_results=gate_results,
                error_message="LLM review unavailable; showing gate results only",
                errors=self._errors,
            )
        except Exception as e:
            self._errors.append(f"Gate collection failed: {e}")

        # Minimal - just an error notice
        return DegradationResult(
            level=DegradationLevel.MINIMAL,
            review_result=None,
            gate_results={},
            error_message="Review infrastructure unavailable. Please retry later.",
            errors=self._errors,
        )

    def _run_full_review(self) -> LLMReviewResult:
        """Run full LLM review with the primary model."""
        reviewer = LLMReviewer(self.anthropic_key)
        return reviewer.review(
            diff=self.diff,
            pr_description=self.pr_description,
            model=self.base_model,
            config=self.config,
            focus_areas=self.focus_areas,
        )

    def _run_reduced_review(self) -> LLMReviewResult:
        """Run reduced review using Haiku for speed and cost efficiency."""
        reviewer = LLMReviewer(self.anthropic_key)
        return reviewer.review(
            diff=self.diff,
            pr_description=self.pr_description,
            model="haiku",
            config=self.config,
            focus_areas=self.focus_areas,
        )

    def _collect_gate_results(self) -> dict[str, Any]:
        """Return previously collected gate results."""
        return self._gate_results
