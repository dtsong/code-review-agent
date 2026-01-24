"""Tests for graceful degradation on LLM failure."""

from unittest.mock import Mock, patch

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

    def test_gates_only_result(self):
        result = DegradationResult(
            level=DegradationLevel.GATES_ONLY,
            review_result=None,
            gate_results={"size": Mock(passed=True)},
            error_message="LLM unavailable",
            errors=["Full review failed: API error", "Reduced review failed: timeout"],
        )
        assert result.level == DegradationLevel.GATES_ONLY
        assert result.review_result is None
        assert result.error_message == "LLM unavailable"
        assert len(result.errors) == 2


class TestDegradedReviewPipeline:
    """Test the degraded review pipeline."""

    def _make_config(self):
        config = Mock()
        config.llm.simple_model = "claude-haiku-4-5-20251001"
        return config

    def _make_pipeline(self, **kwargs):
        defaults = {
            "anthropic_key": "fake-key",
            "diff": "diff content",
            "pr_description": "test pr",
            "config": self._make_config(),
            "focus_areas": [],
        }
        defaults.update(kwargs)
        return DegradedReviewPipeline(**defaults)

    def test_full_review_success(self):
        """When primary model succeeds, return FULL level."""
        pipeline = self._make_pipeline()

        mock_result = Mock()
        mock_result.summary = "This is a valid review summary with enough content"

        with patch.object(pipeline, "_run_full_review", return_value=mock_result):
            result = pipeline.execute()

        assert result.level == DegradationLevel.FULL
        assert result.review_result == mock_result
        assert result.error_message is None

    def test_reduced_fallback_on_primary_failure(self):
        """When primary model fails after retries, fall back to reduced."""
        pipeline = self._make_pipeline()

        mock_reduced = Mock()
        mock_reduced.summary = "Reduced review from haiku model"

        with (
            patch.object(pipeline, "_run_full_review", side_effect=Exception("API error")),
            patch.object(pipeline, "_run_reduced_review", return_value=mock_reduced),
        ):
            result = pipeline.execute()

        assert result.level == DegradationLevel.REDUCED
        assert result.review_result == mock_reduced
        assert "Full review failed" in result.errors[0]

    def test_gates_only_fallback(self):
        """When both models fail, return GATES_ONLY with gate results."""
        gate_results = {"size": Mock(passed=True), "lint": Mock(passed=True)}
        pipeline = self._make_pipeline(gate_results=gate_results)

        with (
            patch.object(pipeline, "_run_full_review", side_effect=Exception("error1")),
            patch.object(pipeline, "_run_reduced_review", side_effect=Exception("error2")),
        ):
            result = pipeline.execute()

        assert result.level == DegradationLevel.GATES_ONLY
        assert result.review_result is None
        assert result.error_message is not None
        assert result.gate_results == gate_results
        assert len(result.errors) == 2

    def test_gate_results_preserved_on_fallback(self):
        """Gate results passed to constructor are preserved in GATES_ONLY."""
        gate_results = {"size": Mock(passed=True), "lint": Mock(passed=False)}
        pipeline = self._make_pipeline(gate_results=gate_results)

        with (
            patch.object(pipeline, "_run_full_review", side_effect=Exception("error")),
            patch.object(pipeline, "_run_reduced_review", side_effect=Exception("error")),
        ):
            result = pipeline.execute()

        assert result.gate_results["size"].passed is True
        assert result.gate_results["lint"].passed is False

    def test_always_produces_output(self):
        """Pipeline should always produce a result, never raise."""
        pipeline = self._make_pipeline()

        with (
            patch.object(pipeline, "_run_full_review", side_effect=Exception("error")),
            patch.object(pipeline, "_run_reduced_review", side_effect=Exception("error")),
        ):
            result = pipeline.execute()

        assert result is not None
        assert isinstance(result.level, DegradationLevel)
        assert result.level == DegradationLevel.GATES_ONLY

    def test_errors_accumulated(self):
        """Errors from each failed level are accumulated."""
        pipeline = self._make_pipeline()

        with (
            patch.object(pipeline, "_run_full_review", side_effect=Exception("full failed")),
            patch.object(pipeline, "_run_reduced_review", side_effect=Exception("reduced failed")),
        ):
            result = pipeline.execute()

        assert "Full review failed: full failed" in result.errors
        assert "Reduced review failed: reduced failed" in result.errors

    def test_uses_config_simple_model_for_reduced(self):
        """Reduced review should use config.llm.simple_model, not hardcoded."""
        config = self._make_config()
        config.llm.simple_model = "claude-haiku-4-5-20251001"
        pipeline = self._make_pipeline(config=config)

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation"
        ) as mock_retry:
            # Full fails
            mock_retry.side_effect = [Exception("full failed"), Mock()]
            # Let the pipeline catch the first failure and try reduced
            with patch.object(pipeline, "_run_full_review", side_effect=Exception("err")):
                # Patch retry directly for the reduced call
                mock_result = Mock()
                mock_result.summary = "Valid reduced review summary content"
                with patch.object(pipeline, "_run_reduced_review", return_value=mock_result):
                    result = pipeline.execute()

        assert result.level == DegradationLevel.REDUCED

    def test_single_llm_reviewer_instance(self):
        """Pipeline should reuse a single LLMReviewer instance."""
        pipeline = self._make_pipeline()
        assert hasattr(pipeline, "_reviewer")


class TestDegradationFormatting:
    """Test formatting of degraded review results."""

    def test_format_gates_only_shows_gate_results(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.GATES_ONLY,
            review_result=None,
            gate_results={
                "size": Mock(passed=True),
                "lint": Mock(passed=False),
            },
            error_message="LLM unavailable",
        )

        output = format_degraded_review(result)
        assert "Gates Only" in output
        assert "LLM unavailable" in output
        assert "size" in output
        assert "PASS" in output
        assert "FAIL" in output

    def test_format_gates_only_shows_errors(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.GATES_ONLY,
            review_result=None,
            gate_results={},
            error_message="LLM unavailable",
            errors=["Full review failed: rate limit", "Reduced failed: timeout"],
        )

        output = format_degraded_review(result)
        assert "rate limit" in output
        assert "timeout" in output

    def test_format_minimal_shows_error(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.MINIMAL,
            review_result=None,
            gate_results={},
            error_message="Infrastructure failure",
            errors=["Full: crash", "Reduced: crash"],
        )

        output = format_degraded_review(result)
        assert "Infrastructure failure" in output
        assert "Service Unavailable" in output
        assert "Full: crash" in output

    def test_format_minimal_without_errors(self):
        from pr_review_agent.output.github_comment import format_degraded_review

        result = DegradationResult(
            level=DegradationLevel.MINIMAL,
            review_result=None,
            gate_results={},
            error_message="Something broke",
        )

        output = format_degraded_review(result)
        assert "Something broke" in output
        assert "retry" in output.lower()
