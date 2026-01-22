"""Pre-analysis step to understand PR characteristics before review."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PRType(Enum):
    """Types of pull requests."""

    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCS = "docs"
    SECURITY = "security"
    DEPENDENCY = "dependency"
    CONFIG = "config"
    UNKNOWN = "unknown"


class RiskLevel(Enum):
    """Risk levels for PRs."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PRAnalysis:
    """Result of pre-analysis."""

    pr_type: PRType
    risk_level: RiskLevel
    complexity: str  # "low", "medium", "high"
    focus_areas: list[str]
    suggested_model: str
    suggested_checks: list[str]
    skip_checks: list[str]


def categorize_files(files: list[str]) -> dict[str, list[str]]:
    """Categorize changed files by type."""
    patterns: dict[str, list[str]] = {
        "test": [],
        "config": [],
        "docs": [],
        "security": [],
        "api": [],
        "ui": [],
        "core": [],
    }

    for f in files:
        f_lower = f.lower()
        if "test" in f_lower or "spec" in f_lower:
            patterns["test"].append(f)
        elif f_lower.endswith((".yml", ".yaml", ".json", ".toml", ".ini", ".env")):
            patterns["config"].append(f)
        elif f_lower.endswith((".md", ".rst", ".txt")) or "doc" in f_lower:
            patterns["docs"].append(f)
        elif any(x in f_lower for x in ["auth", "security", "crypto", "password", "token"]):
            patterns["security"].append(f)
        elif any(x in f_lower for x in ["api", "route", "endpoint", "handler"]):
            patterns["api"].append(f)
        elif any(x in f_lower for x in ["component", "page", "view", "ui"]):
            patterns["ui"].append(f)
        else:
            patterns["core"].append(f)

    return patterns


def infer_pr_type(title: str, description: str, file_patterns: dict[str, list[str]]) -> PRType:
    """Infer PR type from title, description, and file patterns."""
    title_lower = title.lower()

    # Check title for explicit indicators - ORDER MATTERS
    # Check more specific patterns first to avoid false positives

    # Security should be checked early (before "fix" catches "patch")
    if any(x in title_lower for x in ["security", "vuln", "cve"]):
        return PRType.SECURITY

    # Test should come before feature (before "add" catches "test: add")
    if title_lower.startswith("test:") or title_lower.startswith("test "):
        return PRType.TEST
    if any(x in title_lower for x in ["coverage"]):
        return PRType.TEST

    # Bugfix patterns
    if any(x in title_lower for x in ["fix", "bug", "issue", "patch"]):
        return PRType.BUGFIX

    # Feature patterns
    if any(x in title_lower for x in ["feat", "add", "implement", "new"]):
        return PRType.FEATURE

    # Refactor patterns
    if any(x in title_lower for x in ["refactor", "cleanup", "reorganize"]):
        return PRType.REFACTOR

    # Docs patterns
    if any(x in title_lower for x in ["doc", "readme", "comment"]):
        return PRType.DOCS

    # Dependency patterns - check last among title patterns
    if any(x in title_lower for x in ["dep:", "upgrade", "bump"]):
        return PRType.DEPENDENCY

    # Check file patterns if title didn't give us clear indication
    if file_patterns:
        # Test files dominate
        if len(file_patterns.get("test", [])) > len(file_patterns.get("core", [])):
            return PRType.TEST

        # Docs only
        if len(file_patterns.get("docs", [])) > 0 and len(file_patterns.get("core", [])) == 0:
            return PRType.DOCS

        # Security files present
        if len(file_patterns.get("security", [])) > 0:
            return PRType.SECURITY

        # Config files dominate
        if len(file_patterns.get("config", [])) > len(file_patterns.get("core", [])):
            return PRType.CONFIG

    return PRType.FEATURE  # Default


def _get_lines_changed(pr: Any) -> int:
    """Get total lines changed from PR, handling different attribute names."""
    if hasattr(pr, "lines_changed"):
        return pr.lines_changed
    # Fall back to computing from lines_added + lines_removed
    lines_added = getattr(pr, "lines_added", 0)
    lines_removed = getattr(pr, "lines_removed", 0)
    return lines_added + lines_removed


def assess_risk(pr: Any, file_patterns: dict[str, list[str]]) -> RiskLevel:
    """Assess risk level of PR."""
    lines_changed = _get_lines_changed(pr)

    # Critical: security-related files
    if len(file_patterns.get("security", [])) > 0:
        return RiskLevel.CRITICAL

    # High: API changes or large PRs
    if len(file_patterns.get("api", [])) > 3 or lines_changed > 300:
        return RiskLevel.HIGH

    # Medium: core logic changes
    if len(file_patterns.get("core", [])) > 5:
        return RiskLevel.MEDIUM

    # Low: tests, docs, config
    non_core_count = (
        len(file_patterns.get("test", []))
        + len(file_patterns.get("docs", []))
        + len(file_patterns.get("config", []))
    )
    if non_core_count > len(file_patterns.get("core", [])):
        return RiskLevel.LOW

    return RiskLevel.MEDIUM  # Default


def assess_complexity(pr: Any) -> str:
    """Assess PR complexity."""
    # Handle both files_changed as int or list
    files_count = pr.files_changed if isinstance(pr.files_changed, int) else len(pr.files_changed)
    lines_changed = _get_lines_changed(pr)

    if lines_changed >= 200 or files_count > 10:
        return "high"
    if lines_changed > 50 or files_count >= 5:
        return "medium"
    return "low"


def get_focus_areas(pr_type: PRType, risk_level: RiskLevel) -> list[str]:
    """Determine what to focus on during review."""
    base_focus = {
        PRType.FEATURE: ["logic_correctness", "edge_cases", "test_coverage"],
        PRType.BUGFIX: ["root_cause", "regression_risk", "test_coverage"],
        PRType.REFACTOR: ["behavior_preservation", "code_quality", "performance"],
        PRType.TEST: ["coverage_gaps", "test_quality", "assertions"],
        PRType.DOCS: ["accuracy", "completeness", "clarity"],
        PRType.SECURITY: ["vulnerabilities", "auth_logic", "input_validation", "secrets"],
        PRType.DEPENDENCY: ["breaking_changes", "security_advisories", "compatibility"],
        PRType.CONFIG: ["security_implications", "environment_consistency"],
        PRType.UNKNOWN: ["logic_correctness", "code_quality"],
    }

    focus = list(base_focus.get(pr_type, base_focus[PRType.UNKNOWN]))

    # Add security focus for high-risk PRs
    if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
        if "security_implications" not in focus:
            focus.append("security_implications")

    return focus


def get_check_recommendations(
    pr_type: PRType, risk_level: RiskLevel
) -> tuple[list[str], list[str]]:
    """Determine which checks to run and skip."""
    all_checks = ["size_gate", "lint_gate", "security_scan", "test_coverage", "llm_review"]

    # Tests and docs can skip security scan
    if pr_type in [PRType.TEST, PRType.DOCS]:
        return (["size_gate", "lint_gate", "llm_review"], ["security_scan", "test_coverage"])

    # Security PRs should run everything
    if pr_type == PRType.SECURITY or risk_level == RiskLevel.CRITICAL:
        return (all_checks, [])

    # Default: run standard checks
    return (["size_gate", "lint_gate", "llm_review"], ["security_scan"])


def analyze_pr(pr: Any) -> PRAnalysis:
    """Quick analysis to categorize PR and determine review strategy.

    Uses heuristics first, then optional LLM for complex cases.
    """
    # Heuristic analysis based on files changed
    file_patterns = categorize_files(pr.files_changed)

    # Determine PR type
    pr_type = infer_pr_type(pr.title, pr.description, file_patterns)

    # Assess risk level
    risk_level = assess_risk(pr, file_patterns)

    # Calculate complexity
    complexity = assess_complexity(pr)

    # Determine focus areas based on type
    focus_areas = get_focus_areas(pr_type, risk_level)

    # Suggest model based on complexity and risk
    suggested_model = (
        "claude-sonnet-4-20250514"
        if complexity == "high" or risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        else "claude-haiku-4-5-20251001"
    )

    # Determine which checks to run/skip
    suggested_checks, skip_checks = get_check_recommendations(pr_type, risk_level)

    return PRAnalysis(
        pr_type=pr_type,
        risk_level=risk_level,
        complexity=complexity,
        focus_areas=focus_areas,
        suggested_model=suggested_model,
        suggested_checks=suggested_checks,
        skip_checks=skip_checks,
    )
