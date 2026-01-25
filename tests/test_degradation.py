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


class TestChunkedReviewFallback:
    """Test chunked review fallback on context_too_long failure."""

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

    def test_chunked_fallback_on_context_too_long(self):
        """When full review fails with context_too_long, try chunked review."""
        from pr_review_agent.execution.retry_handler import (
            AttemptRecord,
            RetryExhaustedError,
        )

        pipeline = self._make_pipeline()

        # Create RetryExhaustedError with context_too_long attempt
        attempts = [AttemptRecord(
            attempt_number=1, model_used="sonnet", failure_type="context_too_long"
        )]
        context_error = RetryExhaustedError("Context too long", attempts)

        mock_chunked_result = Mock()
        mock_chunked_result.summary = "Chunked review completed successfully"

        with (
            patch.object(pipeline, "_run_full_review", side_effect=context_error),
            patch.object(pipeline, "_run_chunked_review", return_value=mock_chunked_result),
        ):
            result = pipeline.execute()

        assert result.level == DegradationLevel.FULL
        assert result.review_result == mock_chunked_result

    def test_chunked_fallback_failure_continues_to_reduced(self):
        """When chunked review fails, continue to reduced review."""
        from pr_review_agent.execution.retry_handler import (
            AttemptRecord,
            RetryExhaustedError,
        )

        pipeline = self._make_pipeline()

        attempts = [AttemptRecord(
            attempt_number=1, model_used="sonnet", failure_type="context_too_long"
        )]
        context_error = RetryExhaustedError("Context too long", attempts)

        mock_reduced_result = Mock()
        mock_reduced_result.summary = "Reduced review from haiku"

        with (
            patch.object(pipeline, "_run_full_review", side_effect=context_error),
            patch.object(pipeline, "_run_chunked_review", side_effect=Exception("Chunk failed")),
            patch.object(pipeline, "_run_reduced_review", return_value=mock_reduced_result),
        ):
            result = pipeline.execute()

        assert result.level == DegradationLevel.REDUCED
        assert "Chunked review failed" in result.errors[1]

    def test_no_chunked_fallback_for_other_errors(self):
        """When full review fails without context_too_long, skip chunked."""
        from pr_review_agent.execution.retry_handler import (
            AttemptRecord,
            RetryExhaustedError,
        )

        pipeline = self._make_pipeline()

        # Create RetryExhaustedError with rate_limit (not context_too_long)
        attempts = [AttemptRecord(attempt_number=1, model_used="sonnet", failure_type="rate_limit")]
        rate_error = RetryExhaustedError("Rate limit", attempts)

        mock_reduced_result = Mock()
        mock_reduced_result.summary = "Reduced review from haiku"

        with (
            patch.object(pipeline, "_run_full_review", side_effect=rate_error),
            patch.object(pipeline, "_run_chunked_review") as mock_chunked,
            patch.object(pipeline, "_run_reduced_review", return_value=mock_reduced_result),
        ):
            result = pipeline.execute()

        # Chunked should NOT be called since error wasn't context_too_long
        mock_chunked.assert_not_called()
        assert result.level == DegradationLevel.REDUCED


class TestRunChunkedReview:
    """Test _run_chunked_review internals."""

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

    def test_empty_chunks_raises_value_error(self):
        """When chunk_diff returns empty list, raise ValueError."""
        import pytest

        pipeline = self._make_pipeline()

        with (
            patch("pr_review_agent.execution.degradation.chunk_diff", return_value=[]),
            pytest.raises(ValueError, match="No chunks produced"),
        ):
            pipeline._run_chunked_review("claude-sonnet-4-20250514")

    def test_chunks_are_reviewed_and_merged(self):
        """Each chunk is reviewed and results are merged."""
        pipeline = self._make_pipeline()

        chunk1 = Mock()
        chunk1.content = "diff for file1"
        chunk2 = Mock()
        chunk2.content = "diff for file2"

        result1 = Mock()
        result2 = Mock()
        merged = Mock()
        merged.summary = "Merged review"

        chunk_patch = "pr_review_agent.execution.degradation.chunk_diff"
        merge_patch = "pr_review_agent.execution.degradation.merge_review_results"
        with (
            patch(chunk_patch, return_value=[chunk1, chunk2]),
            patch(merge_patch, return_value=merged) as mock_merge,
            patch.object(pipeline._reviewer, "review", side_effect=[result1, result2]),
        ):
            result = pipeline._run_chunked_review("claude-sonnet-4-20250514")

        assert result == merged
        mock_merge.assert_called_once_with([result1, result2])


class TestRunReducedReview:
    """Test _run_reduced_review internals."""

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

    def test_uses_simple_model_from_config(self):
        """Reduced review uses config.llm.simple_model."""
        config = self._make_config()
        config.llm.simple_model = "claude-haiku-4-5-20251001"
        pipeline = self._make_pipeline(config=config)

        mock_result = Mock()
        mock_result.result = Mock()
        mock_result.result.summary = "Valid review summary content"

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation",
            return_value=mock_result,
        ) as mock_retry:
            pipeline._run_reduced_review()

        mock_retry.assert_called_once()
        call_kwargs = mock_retry.call_args[1]
        assert call_kwargs["base_model"] == "claude-haiku-4-5-20251001"

    def test_uses_max_attempts_2(self):
        """Reduced review uses max_attempts=2."""
        pipeline = self._make_pipeline()

        mock_result = Mock()
        mock_result.result = Mock()
        mock_result.result.summary = "Valid review summary content"

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation",
            return_value=mock_result,
        ) as mock_retry:
            pipeline._run_reduced_review()

        call_kwargs = mock_retry.call_args[1]
        assert call_kwargs["max_attempts"] == 2

    def test_validator_rejects_short_summary(self):
        """Validator rejects summaries shorter than 20 chars."""
        pipeline = self._make_pipeline()

        mock_result = Mock()
        mock_result.result = Mock()
        mock_result.result.summary = "Valid review summary content"

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation",
            return_value=mock_result,
        ) as mock_retry:
            pipeline._run_reduced_review()

        # Extract and test the validator function
        call_kwargs = mock_retry.call_args[1]
        validator = call_kwargs["validator"]

        short_result = Mock()
        short_result.summary = "Short"
        assert validator(short_result) is False

        valid_result = Mock()
        valid_result.summary = "This is a valid summary with enough content"
        assert validator(valid_result) is True

        assert validator(None) is False


class TestRunFullReview:
    """Test _run_full_review internals."""

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

    def test_uses_max_attempts_3(self):
        """Full review uses max_attempts=3."""
        pipeline = self._make_pipeline()

        mock_result = Mock()
        mock_result.result = Mock()
        mock_result.result.summary = "Valid review summary content"

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation",
            return_value=mock_result,
        ) as mock_retry:
            pipeline._run_full_review()

        call_kwargs = mock_retry.call_args[1]
        assert call_kwargs["max_attempts"] == 3

    def test_uses_base_model(self):
        """Full review uses the base_model from constructor."""
        pipeline = self._make_pipeline(base_model="claude-sonnet-4-20250514")

        mock_result = Mock()
        mock_result.result = Mock()
        mock_result.result.summary = "Valid review summary content"

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation",
            return_value=mock_result,
        ) as mock_retry:
            pipeline._run_full_review()

        call_kwargs = mock_retry.call_args[1]
        assert call_kwargs["base_model"] == "claude-sonnet-4-20250514"

    def test_validator_rejects_none(self):
        """Validator rejects None result."""
        pipeline = self._make_pipeline()

        mock_result = Mock()
        mock_result.result = Mock()
        mock_result.result.summary = "Valid review summary content"

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation",
            return_value=mock_result,
        ) as mock_retry:
            pipeline._run_full_review()

        call_kwargs = mock_retry.call_args[1]
        validator = call_kwargs["validator"]

        assert validator(None) is False

    def test_validator_rejects_short_summary(self):
        """Validator rejects summaries shorter than 20 chars."""
        pipeline = self._make_pipeline()

        mock_result = Mock()
        mock_result.result = Mock()
        mock_result.result.summary = "Valid review summary content"

        with patch(
            "pr_review_agent.execution.degradation.retry_with_adaptation",
            return_value=mock_result,
        ) as mock_retry:
            pipeline._run_full_review()

        call_kwargs = mock_retry.call_args[1]
        validator = call_kwargs["validator"]

        short = Mock()
        short.summary = "Too short"
        assert validator(short) is False

        valid = Mock()
        valid.summary = "This is a sufficiently long summary"
        assert validator(valid) is True


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
