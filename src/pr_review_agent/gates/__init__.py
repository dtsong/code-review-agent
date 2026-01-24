"""Gates module for deterministic checks."""

from pr_review_agent.gates.circuit_breaker import (
    CircuitBreakerResult,
    GateStatus,
    GateTimedOutError,
    run_gate_with_breaker,
)
from pr_review_agent.gates.coverage_gate import CoverageGateResult, check_coverage
from pr_review_agent.gates.dependency_gate import DependencyGateResult, check_dependencies
from pr_review_agent.gates.lint_gate import LintGateResult, LintIssue, run_lint
from pr_review_agent.gates.size_gate import SizeGateResult, check_size

__all__ = [
    "CircuitBreakerResult", "GateStatus", "GateTimedOutError", "run_gate_with_breaker",
    "SizeGateResult", "check_size",
    "LintGateResult", "LintIssue", "run_lint",
    "CoverageGateResult", "check_coverage",
    "DependencyGateResult", "check_dependencies",
]
