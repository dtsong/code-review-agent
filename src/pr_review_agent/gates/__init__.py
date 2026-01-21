"""Gates module for deterministic checks."""

from pr_review_agent.gates.lint_gate import LintGateResult, LintIssue, run_lint
from pr_review_agent.gates.size_gate import SizeGateResult, check_size

__all__ = ["SizeGateResult", "check_size", "LintGateResult", "LintIssue", "run_lint"]
