"""Tests for graceful degradation on LLM failure."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from pr_review_agent.execution.degradation import (
    DegradationLevel,
    DegradationResult,
    DegradedReviewPipeline,
)


class TestDegradationLevel:
    """Test DegradationLevel enum."""

    def test_levels_exist(self):
        assert DegradationLevel.FULL.value == "full"
        assert DegradationLevel.REDUCED.value == "reduced"
        assert DegradationLevel.GATES_ONLY.value == "gates_only"
        assert DegradationLevel.MINIMAL.value == "minimal"

    def test_level_ordering(self):
        """Full > Reduced > Gates-only > Minimal."""
        levels = list(DegradationLevel)
        assert levels == [
            DegradationLevel.FULL,
            DegradationLevel.REDUCED,
            DegradationLevel.GATES_ONLY,
            DegradationLevel.MINIMAL,
        ]


class TestDegradationResult:
    """Test DegradationResult dataclass."""

    def test_full_result(self):
        result = DegradationResult(
            level=DegradationLevel.FULL,
            review_result=Mock(),
            gate_results={"size": Mock(), "lint": Mock()},
            error_message=None,
        )
        assert result.level == DegradationLevel.FULL
        assert result.review_result is not None
        assert result.error_message is None

    def test_minimal_result(self):
        result = DegradationResult(
            level=DegradationLevel.MINIMAL,
            review_result=None,
            gate_results={},
            error_message="All LLM providers unavailable",
        )
        assert result.level == DegradationLevel.MINIMAL
        assert result.review_result is None
        assert result.error_message == "All LLM providers unavailable"


class TestDegradedReviewPipeline:
    """Test the degraded review pipeline."""

    def _make_pipeline(self, **kwargs):
        defaults = {
            "anthropic_key": "fake-key",
            "diff": "diff content",
            "pr_description": "test pr",
            "config": Mock(),
            "focus_areas": [],
        }
        defaults.update(kwargs)
        return DegradedReviewPipeline(**defaults)

    def test_full_review_success(self):
        """When primary model succeeds, return FULL level."""
        pipeline = self._make_pipeline()

        mock_result = Mock()
        mock_result.summary = "This is a valid review summary with enough content"

        with patch.object(pipeline, '_run_full_review', return_value=mock_result):
            result = pipeline.execute()

        assert result.level == DegradationLevel.FULL
        assert result.review_result == mock_result
        assert result.error_message is None

    def test_reduced_fallback_on_primary_failure(self):
        """When primary model fails, fall back to Haiku (REDUCED)."""
        pipeline = self._make_pipeline()

        mock_reduced = Mock()
        mock_reduced.summary = "Reduced review from haiku model"

        with patch.object(pipeline, '_run_full_review', side_effect=Exception("API error")):
            with patch.object(pipeline, '_run_reduced_review', return_value=mock_reduced):
                result = pipeline.execute()

        assert result.level == DegradationLevel.REDUCED
        assert result.review_result == mock_reduced

    def test_gates_only_fallback(self):
        """When both models fail, return GATES_ONLY level."""
        pipeline = self._make_pipeline()

        with patch.object(pipeline, '_run_full_review', side_effect=Exception("error")):
            with patch.object(pipeline, '_run_reduced_review', side_effect=Exception("error")):
                result = pipeline.execute()

        assert result.level == DegradationLevel.GATES_ONLY
        assert result.review_result is None
        assert result.error_message is not None

    def test_minimal_on_complete_failure(self):
        """When everything fails including gates, return MINIMAL."""
        pipeline = self._make_pipeline()

        with patch.object(pipeline, '_run_full_review', side_effect=Exception("error")):
            with patch.object(pipeline, '_run_reduced_review', side_effect=Exception("error")):
                with patch.object(pipeline, '_collect_gate_results', side_effect=Exception("error")):
                    result = pipeline.execute()

        assert result.level == DegradationLevel.MINIMAL
        assert result.error_message is not None

    def test_gate_results_collected_on_gates_only(self):
        """Gate results should be captured when degraded to gates-only."""
        pipeline = self._make_pipeline()

        gate_results = {"size": Mock(passed=True), "lint": Mock(passed=True)}

        with patch.object(pipeline, '_run_full_review', side_effect=Exception("error")):
            with patch.object(pipeline, '_run_reduced_review', side_effect=Exception("error")):
                with patch.object(pipeline, '_collect_gate_results', return_value=gate_results):
                    result = pipeline.execute()

        assert result.level == DegradationLevel.GATES_ONLY
        assert result.gate_results == gate_results

    def test_always_produces_output(self):
        """Pipeline should always produce a result, never raise."""
        pipeline = self._make_pipeline()

        # Even with all methods failing, we get MINIMAL
        with patch.object(pipeline, '_run_full_review', side_effect=Exception("error")):
            with patch.object(pipeline, '_run_reduced_review', side_effect=Exception("error")):
                with patch.object(pipeline, '_collect_gate_results', side_effect=Exception("error")):
                    result = pipeline.execute()

        assert result is not None
        assert isinstance(result.level, DegradationLevel)


class TestDegradationFormatting:
    """Test formatting of degraded review results."""

    def test_format_full_level(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.FULL,
            review_result=Mock(
                summary="Good code",
                strengths=["clean"],
                issues=[],
                concerns=[],
                questions=[],
                model="sonnet",
                cost_usd=0.01,
                input_tokens=100,
                output_tokens=50,
            ),
            gate_results={},
            error_message=None,
        )

        output = format_degraded_review(result)
        assert "AI Code Review" in output
        assert "Good code" in output

    def test_format_reduced_level_shows_indicator(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.REDUCED,
            review_result=Mock(
                summary="Reduced review",
                strengths=[],
                issues=[],
                concerns=[],
                questions=[],
                model="haiku",
                cost_usd=0.001,
                input_tokens=50,
                output_tokens=25,
            ),
            gate_results={},
            error_message=None,
        )

        output = format_degraded_review(result)
        assert "Reduced" in output or "reduced" in output

    def test_format_gates_only_shows_gate_results(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.GATES_ONLY,
            review_result=None,
            gate_results={
                "size": Mock(passed=True, message="Under limit"),
                "lint": Mock(passed=False, message="3 issues found"),
            },
            error_message="LLM unavailable",
        )

        output = format_degraded_review(result)
        assert "Gates Only" in output or "gates" in output.lower()
        assert "LLM unavailable" in output

    def test_format_minimal_shows_error(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.MINIMAL,
            review_result=None,
            gate_results={},
            error_message="Infrastructure failure",
        )

        output = format_degraded_review(result)
        assert "Infrastructure failure" in output
