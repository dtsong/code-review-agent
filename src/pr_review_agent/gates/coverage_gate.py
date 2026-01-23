"""Coverage gate to check test coverage delta."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from pr_review_agent.config import Config


@dataclass
class CoverageGateResult:
    """Result of coverage gate check."""

    passed: bool
    current_coverage: float = 0.0
    delta: float = 0.0
    uncovered_lines: list[str] = field(default_factory=list)
    reason: str | None = None
    recommendation: str | None = None


def parse_coverage_xml(report_path: Path) -> tuple[float, list[str]]:
    """Parse pytest-cov XML (Cobertura format) report.

    Returns (coverage_percentage, list of uncovered file:line strings).
    """
    if not report_path.exists():
        return 0.0, []

    tree = ET.parse(report_path)
    root = tree.getroot()

    # Cobertura format: <coverage line-rate="0.85" ...>
    line_rate = float(root.get("line-rate", "0"))
    coverage_pct = line_rate * 100

    # Collect uncovered lines
    uncovered = []
    for package in root.findall(".//package"):
        for cls in package.findall(".//class"):
            filename = cls.get("filename", "")
            for line in cls.findall(".//line"):
                if line.get("hits") == "0":
                    uncovered.append(f"{filename}:{line.get('number')}")

    return coverage_pct, uncovered


def check_coverage(
    report_path: Path,
    base_report_path: Path | None,
    config: Config,
) -> CoverageGateResult:
    """Check coverage against thresholds.

    Args:
        report_path: Path to current coverage XML report.
        base_report_path: Path to base branch coverage XML report (for delta).
        config: Review agent configuration.
    """
    if not config.coverage.enabled:
        return CoverageGateResult(passed=True)

    resolved_path = Path(report_path) if not isinstance(report_path, Path) else report_path
    if not resolved_path.exists():
        return CoverageGateResult(
            passed=True,
            reason="Coverage report not found, skipping check.",
            recommendation="Generate coverage report with: pytest --cov --cov-report=xml",
        )

    current_coverage, uncovered_lines = parse_coverage_xml(resolved_path)

    # Calculate delta if base report exists
    delta = 0.0
    if base_report_path and Path(base_report_path).exists():
        base_coverage, _ = parse_coverage_xml(Path(base_report_path))
        delta = current_coverage - base_coverage

    # Check minimum coverage threshold
    min_coverage = config.coverage.min_coverage
    if current_coverage < min_coverage:
        return CoverageGateResult(
            passed=False,
            current_coverage=current_coverage,
            delta=delta,
            uncovered_lines=uncovered_lines[:20],  # Limit output
            reason=f"Coverage {current_coverage:.1f}% is below minimum {min_coverage}%",
            recommendation=f"Increase test coverage to at least {min_coverage}%.",
        )

    # Check coverage decrease
    if config.coverage.fail_on_decrease and delta < 0:
        return CoverageGateResult(
            passed=False,
            current_coverage=current_coverage,
            delta=delta,
            uncovered_lines=uncovered_lines[:20],
            reason=f"Coverage decreased by {abs(delta):.1f}% ({current_coverage:.1f}%)",
            recommendation="Add tests to maintain or improve coverage.",
        )

    return CoverageGateResult(
        passed=True,
        current_coverage=current_coverage,
        delta=delta,
        uncovered_lines=uncovered_lines[:20],
    )
