"""Circuit breaker for gate tools to prevent hanging on external tool failures."""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GateStatus(Enum):
    """Status of a gate after circuit breaker evaluation."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class GateTimedOutError(Exception):
    """Raised when a gate exceeds its timeout."""


@dataclass
class CircuitBreakerResult:
    """Result of running a gate through the circuit breaker."""

    status: GateStatus
    gate_result: Any = None
    elapsed_ms: int = 0
    reason: str | None = None


def run_gate_with_breaker[T](
    gate_fn: Callable[[], T],
    timeout: float,
) -> CircuitBreakerResult:
    """Run a gate function with a timeout circuit breaker.

    Args:
        gate_fn: Zero-arg callable that returns a gate result.
        timeout: Maximum seconds to wait before skipping the gate.

    Returns:
        CircuitBreakerResult with status, gate_result, and elapsed_ms.
    """
    start = time.monotonic()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(gate_fn)
            result = future.result(timeout=timeout)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        status = GateStatus.PASSED if result.passed else GateStatus.FAILED
        return CircuitBreakerResult(
            status=status,
            gate_result=result,
            elapsed_ms=elapsed_ms,
        )

    except FuturesTimeoutError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return CircuitBreakerResult(
            status=GateStatus.SKIPPED,
            gate_result=None,
            elapsed_ms=elapsed_ms,
            reason=f"Gate timed out after {timeout}s",
        )

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return CircuitBreakerResult(
            status=GateStatus.SKIPPED,
            gate_result=None,
            elapsed_ms=elapsed_ms,
            reason=str(e),
        )
