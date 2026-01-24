"""Tests for circuit breaker gate wrapper."""

import time

from pr_review_agent.config import CircuitBreakerConfig, Config
from pr_review_agent.gates.circuit_breaker import (
    CircuitBreakerResult,
    GateStatus,
    run_gate_with_breaker,
)
from pr_review_agent.gates.lint_gate import LintGateResult
from pr_review_agent.gates.security_gate import SecurityGateResult


def test_gate_status_enum():
    """GateStatus should have PASSED, FAILED, SKIPPED values."""
    assert GateStatus.PASSED.value == "passed"
    assert GateStatus.FAILED.value == "failed"
    assert GateStatus.SKIPPED.value == "skipped"


def test_successful_gate_returns_result():
    """A gate that completes within timeout returns its result."""
    def fast_gate():
        return LintGateResult(passed=True)

    config = CircuitBreakerConfig(lint_timeout=30)
    result = run_gate_with_breaker(fast_gate, timeout=config.lint_timeout)

    assert result.status == GateStatus.PASSED
    assert result.gate_result is not None
    assert result.gate_result.passed is True
    assert result.elapsed_ms >= 0


def test_failed_gate_returns_failed_status():
    """A gate that fails within timeout returns FAILED status."""
    def failing_gate():
        return LintGateResult(passed=False, recommendation="Fix lint errors")

    config = CircuitBreakerConfig(lint_timeout=30)
    result = run_gate_with_breaker(failing_gate, timeout=config.lint_timeout)

    assert result.status == GateStatus.FAILED
    assert result.gate_result is not None
    assert result.gate_result.passed is False


def test_timed_out_gate_returns_skipped():
    """A gate that exceeds timeout returns SKIPPED status."""
    def slow_gate():
        time.sleep(5)
        return LintGateResult(passed=True)

    result = run_gate_with_breaker(slow_gate, timeout=0.1)

    assert result.status == GateStatus.SKIPPED
    assert result.gate_result is None
    assert "timed out" in result.reason.lower()


def test_gate_exception_returns_skipped():
    """A gate that raises an exception returns SKIPPED status."""
    def broken_gate():
        raise RuntimeError("Tool crashed")

    result = run_gate_with_breaker(broken_gate, timeout=30)

    assert result.status == GateStatus.SKIPPED
    assert result.gate_result is None
    assert "Tool crashed" in result.reason


def test_elapsed_ms_tracks_duration():
    """elapsed_ms should approximate actual gate duration."""
    def timed_gate():
        time.sleep(0.05)
        return LintGateResult(passed=True)

    result = run_gate_with_breaker(timed_gate, timeout=5)

    assert result.elapsed_ms >= 40  # at least ~50ms minus tolerance


def test_default_timeouts_from_config():
    """CircuitBreakerConfig should have sensible defaults."""
    config = CircuitBreakerConfig()

    assert config.lint_timeout == 30
    assert config.security_timeout == 60
    assert config.coverage_timeout == 45
    assert config.dependency_timeout == 20


def test_custom_timeouts():
    """CircuitBreakerConfig accepts custom timeout values."""
    config = CircuitBreakerConfig(
        lint_timeout=10,
        security_timeout=120,
        coverage_timeout=90,
        dependency_timeout=5,
    )

    assert config.lint_timeout == 10
    assert config.security_timeout == 120
    assert config.coverage_timeout == 90
    assert config.dependency_timeout == 5


def test_skipped_gate_allows_pipeline_to_continue():
    """A skipped gate should not block the review pipeline."""
    def hanging_gate():
        time.sleep(5)
        return SecurityGateResult(passed=True)

    result = run_gate_with_breaker(hanging_gate, timeout=0.1)

    # Pipeline can check status and continue
    assert result.status == GateStatus.SKIPPED
    # The pipeline should treat SKIPPED as non-blocking
    assert result.status != GateStatus.FAILED


def test_circuit_breaker_result_fields():
    """CircuitBreakerResult should have all required fields."""
    result = CircuitBreakerResult(
        status=GateStatus.SKIPPED,
        gate_result=None,
        elapsed_ms=150,
        reason="Gate timed out after 0.1s",
    )

    assert result.status == GateStatus.SKIPPED
    assert result.gate_result is None
    assert result.elapsed_ms == 150
    assert result.reason == "Gate timed out after 0.1s"


def test_passed_result_has_no_reason():
    """A passed gate should have no reason field set."""
    result = CircuitBreakerResult(
        status=GateStatus.PASSED,
        gate_result=LintGateResult(passed=True),
        elapsed_ms=10,
    )

    assert result.reason is None


def test_circuit_breaker_config_in_main_config():
    """CircuitBreakerConfig should be accessible from main Config."""
    config = Config()
    assert hasattr(config, "circuit_breaker")
    assert isinstance(config.circuit_breaker, CircuitBreakerConfig)


def test_multiple_gates_independent_timeouts():
    """Each gate type should use its own configured timeout."""
    config = CircuitBreakerConfig(lint_timeout=0.1, security_timeout=5)

    def slow_gate():
        time.sleep(1)
        return LintGateResult(passed=True)

    # Lint gate with short timeout should skip
    lint_result = run_gate_with_breaker(slow_gate, timeout=config.lint_timeout)
    assert lint_result.status == GateStatus.SKIPPED

    # Security gate with long timeout should pass (gate only sleeps 1s)
    def medium_gate():
        time.sleep(0.05)
        return SecurityGateResult(passed=True)

    sec_result = run_gate_with_breaker(medium_gate, timeout=config.security_timeout)
    assert sec_result.status == GateStatus.PASSED
