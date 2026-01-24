"""Tests for per-attempt observability logging in retry handler."""

from unittest.mock import MagicMock, patch

import anthropic

from pr_review_agent.execution.retry_handler import (
    AttemptRecord,
    RetryResult,
    RetryStrategy,
    retry_with_adaptation,
)
from pr_review_agent.metrics.supabase_logger import SupabaseLogger


class TestAttemptRecord:
    """Test AttemptRecord captures correct data."""

    def test_successful_attempt_records_basic_fields(self):
        """First attempt succeeds - record captures attempt number, model, latency."""
        result = MagicMock()

        def operation(strategy: RetryStrategy):
            return result

        retry_result = retry_with_adaptation(
            operation=operation,
            base_model="claude-sonnet-4-20250514",
            max_attempts=3,
        )

        assert retry_result.result is result
        assert len(retry_result.attempts) == 1
        attempt = retry_result.attempts[0]
        assert attempt.attempt_number == 1
        assert attempt.model_used == "claude-sonnet-4-20250514"
        assert attempt.failure_type is None
        assert attempt.strategy_applied is None
        assert attempt.latency_ms >= 0

    def test_retry_after_rate_limit(self):
        """Rate limit on first attempt, success on second."""
        call_count = 0

        def operation(strategy: RetryStrategy):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise anthropic.RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429),
                    body={"error": {"message": "rate limited"}},
                )
            return "success"

        with patch("pr_review_agent.execution.retry_handler.time.sleep"):
            retry_result = retry_with_adaptation(
                operation=operation,
                base_model="claude-sonnet-4-20250514",
                max_attempts=3,
            )

        assert retry_result.result == "success"
        assert len(retry_result.attempts) == 2

        # First attempt failed with rate limit
        assert retry_result.attempts[0].attempt_number == 1
        assert retry_result.attempts[0].failure_type == "rate_limit"
        assert retry_result.attempts[0].model_used == "claude-sonnet-4-20250514"

        # Second attempt succeeded with adapted strategy
        assert retry_result.attempts[1].attempt_number == 2
        assert retry_result.attempts[1].failure_type is None

    def test_retry_after_context_too_long(self):
        """Context overflow on first attempt triggers strategy adaptation."""
        call_count = 0

        def operation(strategy: RetryStrategy):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise anthropic.BadRequestError(
                    message="context length exceeded",
                    response=MagicMock(status_code=400),
                    body={"error": {"message": "context length exceeded"}},
                )
            return "success"

        with patch("pr_review_agent.execution.retry_handler.time.sleep"):
            retry_result = retry_with_adaptation(
                operation=operation,
                base_model="claude-sonnet-4-20250514",
                max_attempts=3,
            )

        assert retry_result.attempts[0].failure_type == "context_too_long"
        assert retry_result.attempts[1].strategy_applied is not None
        assert "summarize" in retry_result.attempts[1].strategy_applied

    def test_retry_after_api_error(self):
        """Generic API error recorded."""
        call_count = 0

        def operation(strategy: RetryStrategy):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise anthropic.APIError(
                    message="internal error",
                    request=MagicMock(),
                    body={"error": {"message": "internal error"}},
                )
            return "success"

        with patch("pr_review_agent.execution.retry_handler.time.sleep"):
            retry_result = retry_with_adaptation(
                operation=operation,
                base_model="claude-sonnet-4-20250514",
                max_attempts=3,
            )

        assert retry_result.attempts[0].failure_type == "api_error"

    def test_low_quality_response_recorded(self):
        """Validator rejection recorded as low_quality_response."""
        call_count = 0

        def operation(strategy: RetryStrategy):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "bad"
            return "good"

        def validator(result):
            return result == "good"

        with patch("pr_review_agent.execution.retry_handler.time.sleep"):
            retry_result = retry_with_adaptation(
                operation=operation,
                base_model="claude-sonnet-4-20250514",
                max_attempts=3,
                validator=validator,
            )

        assert retry_result.attempts[0].failure_type == "low_quality_response"
        assert retry_result.attempts[1].failure_type is None

    def test_all_attempts_exhausted(self):
        """All attempts fail - all recorded before raising."""
        def operation(strategy: RetryStrategy):
            raise anthropic.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429),
                body={"error": {"message": "rate limited"}},
            )

        with patch("pr_review_agent.execution.retry_handler.time.sleep"):
            try:
                retry_with_adaptation(
                    operation=operation,
                    base_model="claude-sonnet-4-20250514",
                    max_attempts=3,
                )
            except Exception as e:
                # The exception should carry the attempts
                assert hasattr(e, "attempts")
                assert len(e.attempts) == 3
                assert all(a.failure_type == "rate_limit" for a in e.attempts)

    def test_latency_measured(self):
        """Latency is measured for each attempt."""
        def operation(strategy: RetryStrategy):
            return "result"

        retry_result = retry_with_adaptation(
            operation=operation,
            base_model="claude-sonnet-4-20250514",
            max_attempts=1,
        )

        assert retry_result.attempts[0].latency_ms >= 0

    def test_strategy_recorded_on_adapted_attempt(self):
        """When strategy is adapted, it's recorded."""
        call_count = 0

        def operation(strategy: RetryStrategy):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise anthropic.RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429),
                    body={"error": {"message": "rate limited"}},
                )
            return "success"

        with patch("pr_review_agent.execution.retry_handler.time.sleep"):
            retry_result = retry_with_adaptation(
                operation=operation,
                base_model="claude-sonnet-4-20250514",
                max_attempts=3,
            )

        # Second attempt should have strategy info
        assert retry_result.attempts[1].strategy_applied is not None


class TestRetryResult:
    """Test RetryResult structure."""

    def test_total_latency(self):
        """Total latency sums all attempt latencies."""
        result = RetryResult(
            result="ok",
            attempts=[
                AttemptRecord(attempt_number=1, model_used="m", latency_ms=100),
                AttemptRecord(attempt_number=2, model_used="m", latency_ms=200),
            ],
        )
        assert result.total_latency_ms == 300

    def test_was_retried(self):
        """was_retried is True when more than one attempt."""
        single = RetryResult(
            result="ok",
            attempts=[AttemptRecord(attempt_number=1, model_used="m", latency_ms=50)],
        )
        assert single.was_retried is False

        multi = RetryResult(
            result="ok",
            attempts=[
                AttemptRecord(attempt_number=1, model_used="m", latency_ms=50),
                AttemptRecord(attempt_number=2, model_used="m", latency_ms=50),
            ],
        )
        assert multi.was_retried is True


class TestSupabaseAttemptLogging:
    """Test logging attempts to Supabase."""

    def test_log_attempts_inserts_records(self):
        """Each attempt is logged as a separate row."""
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "abc"}]
        )

        with patch(
            "pr_review_agent.metrics.supabase_logger.create_client",
            return_value=mock_client,
        ):
            logger = SupabaseLogger("http://test", "key")
            attempts = [
                AttemptRecord(
                    attempt_number=1,
                    model_used="claude-sonnet-4-20250514",
                    failure_type="rate_limit",
                    strategy_applied=None,
                    latency_ms=150,
                ),
                AttemptRecord(
                    attempt_number=2,
                    model_used="claude-haiku-4-5-20251001",
                    failure_type=None,
                    strategy_applied="model_downgrade",
                    latency_ms=200,
                ),
            ]

            logger.log_attempts(review_id="review-123", attempts=attempts)

            # Should insert to review_attempts table
            mock_client.table.assert_called_with("review_attempts")
            insert_call = mock_client.table.return_value.insert
            inserted_data = insert_call.call_args[0][0]
            assert len(inserted_data) == 2
            assert inserted_data[0]["attempt_number"] == 1
            assert inserted_data[0]["failure_type"] == "rate_limit"
            assert inserted_data[0]["review_id"] == "review-123"
            assert inserted_data[1]["attempt_number"] == 2
            assert inserted_data[1]["model_used"] == "claude-haiku-4-5-20251001"

    def test_log_attempts_handles_error_gracefully(self):
        """Logging failure doesn't raise."""
        mock_client = MagicMock()
        mock_client.table.return_value.insert.side_effect = Exception("db error")

        with patch(
            "pr_review_agent.metrics.supabase_logger.create_client",
            return_value=mock_client,
        ):
            logger = SupabaseLogger("http://test", "key")
            attempts = [
                AttemptRecord(attempt_number=1, model_used="m", latency_ms=100),
            ]

            # Should not raise
            logger.log_attempts(review_id="review-123", attempts=attempts)
