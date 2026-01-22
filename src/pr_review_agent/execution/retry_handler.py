"""Intelligent retry handler with exponential backoff and strategy adaptation."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar

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


def get_backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 1s, 2s, 4s, 8s... capped at 30s."""
    return min(2**attempt, 30)


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
) -> T:
    """Execute operation with intelligent retries.

    Args:
        operation: Function that takes RetryStrategy and returns result
        base_model: Starting model to use
        max_attempts: Maximum retry attempts
        validator: Optional function to validate response quality

    Returns:
        Result from operation

    Raises:
        Exception: If all retries exhausted
    """
    context = RetryContext(max_attempts=max_attempts)
    last_error = None

    while context.attempt < context.max_attempts:
        strategy = adapt_strategy(context, base_model)

        try:
            result = operation(strategy)

            # Validate response if validator provided
            if validator and not validator(result):
                context.failures.append(FailureType.LOW_QUALITY_RESPONSE)
                context.attempt += 1
                continue

            return result

        except anthropic.RateLimitError:
            context.failures.append(FailureType.RATE_LIMIT)
            last_error = "Rate limit exceeded"

        except anthropic.BadRequestError as e:
            if "context length" in str(e).lower():
                context.failures.append(FailureType.CONTEXT_TOO_LONG)
                last_error = "Context too long"
            else:
                raise

        except anthropic.AuthenticationError:
            # Auth errors should not be retried
            raise

        except anthropic.APIError as e:
            context.failures.append(FailureType.API_ERROR)
            last_error = str(e)

        context.attempt += 1

        if context.attempt < context.max_attempts:
            backoff = get_backoff_seconds(context.attempt)
            print(f"Retry {context.attempt}/{context.max_attempts} after {backoff}s ({last_error})")
            time.sleep(backoff)

    raise Exception(f"All {max_attempts} attempts failed. Last error: {last_error}")
