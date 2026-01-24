"""Intelligent retry handler with exponential backoff and strategy adaptation."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

import anthropic


class FailureType(Enum):
    """Types of failures that can occur during LLM calls."""

    RATE_LIMIT = "rate_limit"
    CONTEXT_TOO_LONG = "context_too_long"
    API_ERROR = "api_error"
    LOW_QUALITY_RESPONSE = "low_quality_response"
    TIMEOUT = "timeout"


@dataclass
class RetryContext:
    """Context for tracking retry attempts and failures."""

    attempt: int = 0
    max_attempts: int = 3
    failures: list[FailureType] = field(default_factory=list)


@dataclass
class RetryStrategy:
    """Adapted strategy based on failures."""

    model: str
    max_tokens: int
    temperature: float
    summarize_diff: bool = False
    chunk_files: bool = False


@dataclass
class AttemptRecord:
    """Record of a single retry attempt for observability."""

    attempt_number: int
    model_used: str
    latency_ms: int = 0
    failure_type: str | None = None
    strategy_applied: str | None = None


@dataclass
class RetryResult:
    """Result from retry_with_adaptation including attempt records."""

    result: object
    attempts: list[AttemptRecord] = field(default_factory=list)

    @property
    def total_latency_ms(self) -> int:
        """Sum of all attempt latencies."""
        return sum(a.latency_ms for a in self.attempts)

    @property
    def was_retried(self) -> bool:
        """Whether more than one attempt was needed."""
        return len(self.attempts) > 1


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, attempts: list[AttemptRecord]):
        super().__init__(message)
        self.attempts = attempts


def get_backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 1s, 2s, 4s, 8s... capped at 30s."""
    return min(2**attempt, 30)


def _describe_strategy(strategy: RetryStrategy, context: RetryContext) -> str | None:
    """Describe the adaptation applied to a strategy."""
    if context.attempt == 0:
        return None
    parts = []
    if strategy.summarize_diff:
        parts.append("summarize_diff")
    if strategy.chunk_files:
        parts.append("chunk_files")
    if strategy.temperature > 0:
        parts.append(f"temp={strategy.temperature}")
    if FailureType.RATE_LIMIT in context.failures:
        parts.append("model_downgrade")
    return ", ".join(parts) if parts else None


def adapt_strategy(context: RetryContext, base_model: str) -> RetryStrategy:
    """Adapt strategy based on what failed."""
    strategy = RetryStrategy(
        model=base_model,
        max_tokens=4096,
        temperature=0.0,
    )

    if FailureType.CONTEXT_TOO_LONG in context.failures:
        # Diff too big - summarize it
        strategy.summarize_diff = True
        strategy.chunk_files = True

    if FailureType.LOW_QUALITY_RESPONSE in context.failures:
        # Bad response - try with higher temp for variety
        strategy.temperature = 0.3

    if FailureType.RATE_LIMIT in context.failures:
        # Rate limited - fall back to smaller model
        if "sonnet" in strategy.model:
            strategy.model = "claude-haiku-4-5-20251001"

    return strategy


T = TypeVar("T")


def retry_with_adaptation(
    operation: Callable[[RetryStrategy], T],
    base_model: str,
    max_attempts: int = 3,
    validator: Callable[[T], bool] | None = None,
) -> RetryResult:
    """Execute operation with intelligent retries.

    Args:
        operation: Function that takes RetryStrategy and returns result
        base_model: Starting model to use
        max_attempts: Maximum retry attempts
        validator: Optional function to validate response quality

    Returns:
        RetryResult with the operation result and attempt records.

    Raises:
        RetryExhaustedError: If all retries exhausted (includes attempt records).
    """
    context = RetryContext(max_attempts=max_attempts)
    last_error = None
    attempt_records: list[AttemptRecord] = []

    while context.attempt < context.max_attempts:
        strategy = adapt_strategy(context, base_model)
        strategy_desc = _describe_strategy(strategy, context)
        start_time = time.monotonic()

        try:
            result = operation(strategy)

            # Validate response if validator provided
            if validator and not validator(result):
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                attempt_records.append(AttemptRecord(
                    attempt_number=context.attempt + 1,
                    model_used=strategy.model,
                    latency_ms=elapsed_ms,
                    failure_type="low_quality_response",
                    strategy_applied=strategy_desc,
                ))
                context.failures.append(FailureType.LOW_QUALITY_RESPONSE)
                context.attempt += 1
                continue

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            attempt_records.append(AttemptRecord(
                attempt_number=context.attempt + 1,
                model_used=strategy.model,
                latency_ms=elapsed_ms,
                failure_type=None,
                strategy_applied=strategy_desc,
            ))

            return RetryResult(result=result, attempts=attempt_records)

        except anthropic.RateLimitError:
            context.failures.append(FailureType.RATE_LIMIT)
            last_error = "Rate limit exceeded"
            failure = "rate_limit"

        except anthropic.BadRequestError as e:
            if "context length" in str(e).lower():
                context.failures.append(FailureType.CONTEXT_TOO_LONG)
                last_error = "Context too long"
                failure = "context_too_long"
            else:
                raise

        except anthropic.AuthenticationError:
            # Auth errors should not be retried
            raise

        except anthropic.APIError as e:
            context.failures.append(FailureType.API_ERROR)
            last_error = str(e)
            failure = "api_error"

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        attempt_records.append(AttemptRecord(
            attempt_number=context.attempt + 1,
            model_used=strategy.model,
            latency_ms=elapsed_ms,
            failure_type=failure,
            strategy_applied=strategy_desc,
        ))

        context.attempt += 1

        if context.attempt < context.max_attempts:
            backoff = get_backoff_seconds(context.attempt)
            print(
                f"Retry {context.attempt}/{context.max_attempts} "
                f"after {backoff}s ({last_error})"
            )
            time.sleep(backoff)

    raise RetryExhaustedError(
        f"All {max_attempts} attempts failed. Last error: {last_error}",
        attempts=attempt_records,
    )
