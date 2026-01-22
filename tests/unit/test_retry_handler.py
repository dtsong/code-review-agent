"""Unit tests for retry handler."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from pr_review_agent.execution.retry_handler import (
    RetryContext,
    RetryStrategy,
    FailureType,
    get_backoff_seconds,
    adapt_strategy,
    retry_with_adaptation,
)


class TestBackoff:
    """Test exponential backoff calculation."""

    def test_backoff_increases_exponentially(self):
        assert get_backoff_seconds(0) == 1
        assert get_backoff_seconds(1) == 2
        assert get_backoff_seconds(2) == 4
        assert get_backoff_seconds(3) == 8

    def test_backoff_caps_at_30_seconds(self):
        assert get_backoff_seconds(10) == 30
        assert get_backoff_seconds(100) == 30


class TestRetryContext:
    """Test RetryContext initialization."""

    def test_default_initialization(self):
        context = RetryContext()
        assert context.attempt == 0
        assert context.max_attempts == 3
        assert context.failures == []

    def test_custom_initialization(self):
        context = RetryContext(attempt=2, max_attempts=5, failures=[FailureType.RATE_LIMIT])
        assert context.attempt == 2
        assert context.max_attempts == 5
        assert FailureType.RATE_LIMIT in context.failures


class TestRetryStrategy:
    """Test RetryStrategy dataclass."""

    def test_default_strategy(self):
        strategy = RetryStrategy(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=0.0,
        )
        assert strategy.model == "claude-sonnet-4-20250514"
        assert strategy.max_tokens == 4096
        assert strategy.temperature == 0.0
        assert strategy.summarize_diff is False
        assert strategy.chunk_files is False


class TestAdaptStrategy:
    """Test strategy adaptation based on failures."""

    def test_no_failures_returns_base_strategy(self):
        context = RetryContext(attempt=0, failures=[])
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")

        assert strategy.model == "claude-sonnet-4-20250514"
        assert strategy.summarize_diff is False
        assert strategy.chunk_files is False

    def test_context_too_long_enables_summarization(self):
        context = RetryContext(attempt=1, failures=[FailureType.CONTEXT_TOO_LONG])
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")

        assert strategy.summarize_diff is True
        assert strategy.chunk_files is True

    def test_rate_limit_falls_back_to_haiku(self):
        context = RetryContext(attempt=1, failures=[FailureType.RATE_LIMIT])
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")

        assert strategy.model == "claude-haiku-4-5-20251001"

    def test_rate_limit_keeps_haiku_if_already_haiku(self):
        """If already using Haiku, don't change model on rate limit."""
        context = RetryContext(attempt=1, failures=[FailureType.RATE_LIMIT])
        strategy = adapt_strategy(context, "claude-haiku-4-5-20251001")

        assert strategy.model == "claude-haiku-4-5-20251001"

    def test_low_quality_increases_temperature(self):
        context = RetryContext(attempt=1, failures=[FailureType.LOW_QUALITY_RESPONSE])
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")

        assert strategy.temperature == 0.3

    def test_multiple_failures_compound(self):
        context = RetryContext(
            attempt=2, failures=[FailureType.RATE_LIMIT, FailureType.CONTEXT_TOO_LONG]
        )
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")

        assert strategy.model == "claude-haiku-4-5-20251001"
        assert strategy.summarize_diff is True

    def test_api_error_does_not_change_strategy(self):
        """API errors should retry with same strategy."""
        context = RetryContext(attempt=1, failures=[FailureType.API_ERROR])
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")

        assert strategy.model == "claude-sonnet-4-20250514"
        assert strategy.summarize_diff is False
        assert strategy.temperature == 0.0


class TestRetryWithAdaptation:
    """Test the main retry function."""

    def test_success_on_first_attempt(self):
        operation = Mock(return_value="success")

        result = retry_with_adaptation(
            operation=operation, base_model="claude-sonnet-4-20250514", max_attempts=3
        )

        assert result == "success"
        assert operation.call_count == 1

    def test_retries_on_rate_limit(self):
        """Test that rate limit errors trigger retry."""
        import anthropic

        # Create mock rate limit error
        mock_response = Mock()
        mock_response.status_code = 429
        rate_limit_error = anthropic.RateLimitError(
            "rate limited", response=mock_response, body={}
        )

        operation = Mock(side_effect=[rate_limit_error, "success"])

        with patch("time.sleep"):  # Don't actually sleep in tests
            result = retry_with_adaptation(
                operation=operation, base_model="claude-sonnet-4-20250514", max_attempts=3
            )

        assert result == "success"
        assert operation.call_count == 2

    def test_retries_on_context_too_long(self):
        """Test that context length errors trigger retry with summarization."""
        import anthropic

        mock_response = Mock()
        mock_response.status_code = 400
        context_error = anthropic.BadRequestError(
            "context length exceeded", response=mock_response, body={}
        )

        strategies_used = []

        def track_strategy(strategy):
            strategies_used.append(strategy)
            if len(strategies_used) < 2:
                raise context_error
            return "success"

        with patch("time.sleep"):
            result = retry_with_adaptation(
                operation=track_strategy,
                base_model="claude-sonnet-4-20250514",
                max_attempts=3,
            )

        assert result == "success"
        assert len(strategies_used) == 2
        # Second strategy should have summarize_diff enabled
        assert strategies_used[1].summarize_diff is True

    def test_retries_on_validation_failure(self):
        operation = Mock(side_effect=["bad", "bad", "good"])
        validator = Mock(side_effect=[False, False, True])

        result = retry_with_adaptation(
            operation=operation,
            base_model="claude-sonnet-4-20250514",
            max_attempts=3,
            validator=validator,
        )

        assert result == "good"
        assert operation.call_count == 3

    def test_raises_after_max_attempts(self):
        import anthropic

        mock_response = Mock()
        mock_response.status_code = 429
        rate_limit_error = anthropic.RateLimitError(
            "rate limited", response=mock_response, body={}
        )

        operation = Mock(side_effect=rate_limit_error)

        with patch("time.sleep"):
            with pytest.raises(Exception) as exc_info:
                retry_with_adaptation(
                    operation=operation,
                    base_model="claude-sonnet-4-20250514",
                    max_attempts=3,
                )

        assert "All 3 attempts failed" in str(exc_info.value)
        assert operation.call_count == 3

    def test_raises_on_non_retryable_error(self):
        """Non-retryable errors should propagate immediately."""
        import anthropic

        mock_response = Mock()
        mock_response.status_code = 401
        auth_error = anthropic.AuthenticationError(
            "invalid api key", response=mock_response, body={}
        )

        operation = Mock(side_effect=auth_error)

        with pytest.raises(anthropic.AuthenticationError):
            retry_with_adaptation(
                operation=operation, base_model="claude-sonnet-4-20250514", max_attempts=3
            )

        # Should not retry auth errors
        assert operation.call_count == 1

    def test_backoff_is_applied_between_retries(self):
        """Verify exponential backoff is applied."""
        import anthropic

        mock_response = Mock()
        mock_response.status_code = 429
        rate_limit_error = anthropic.RateLimitError(
            "rate limited", response=mock_response, body={}
        )

        operation = Mock(side_effect=[rate_limit_error, rate_limit_error, "success"])
        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("time.sleep", side_effect=mock_sleep):
            result = retry_with_adaptation(
                operation=operation, base_model="claude-sonnet-4-20250514", max_attempts=3
            )

        assert result == "success"
        # Should have slept twice (after first and second failure)
        assert len(sleep_calls) == 2
        # Backoff should increase (1 -> 2 seconds)
        assert sleep_calls[0] < sleep_calls[1]

    def test_strategy_passed_to_operation(self):
        """Verify the strategy is correctly passed to the operation."""
        received_strategy = None

        def capture_strategy(strategy):
            nonlocal received_strategy
            received_strategy = strategy
            return "success"

        retry_with_adaptation(
            operation=capture_strategy,
            base_model="claude-sonnet-4-20250514",
            max_attempts=3,
        )

        assert received_strategy is not None
        assert received_strategy.model == "claude-sonnet-4-20250514"
        assert received_strategy.max_tokens == 4096
