"""Security gate using Bandit."""

import json
import subprocess
from dataclasses import dataclass, field

from pr_review_agent.config import Config

SEVERITY_ORDER = ["low", "medium", "high", "critical"]


@dataclass
class SecurityFinding:
    """Single security finding."""

    file: str
    line: int
    severity: str
    confidence: str
    test_id: str
    message: str


@dataclass
class SecurityGateResult:
    """Result of security gate check."""

    passed: bool
    findings: list[SecurityFinding] = field(default_factory=list)
    severity_counts: dict[str, int] = field(default_factory=lambda: {
        "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0
    })
    recommendation: str | None = None


def _severity_meets_threshold(severity: str, threshold: str) -> bool:
    """Check if a severity level meets or exceeds the threshold."""
    sev_lower = severity.lower()
    thresh_lower = threshold.lower()
    if sev_lower not in SEVERITY_ORDER or thresh_lower not in SEVERITY_ORDER:
        return False
    return SEVERITY_ORDER.index(sev_lower) >= SEVERITY_ORDER.index(thresh_lower)


def run_security_scan(files: list[str], config: Config) -> SecurityGateResult:
    """Run Bandit security scan on the specified files."""
    if not config.security.enabled:
        return SecurityGateResult(passed=True)

    if not files:
        return SecurityGateResult(passed=True)

    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return SecurityGateResult(passed=True)

    try:
        result = subprocess.run(
            ["bandit", "-f", "json", "-q", *py_files],
            capture_output=True,
            text=True,
        )

        findings: list[SecurityFinding] = []
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

        output = result.stdout or result.stderr
        if output:
            try:
                bandit_output = json.loads(output)
                for item in bandit_output.get("results", []):
                    severity = item.get("issue_severity", "LOW").upper()
                    finding = SecurityFinding(
                        file=item.get("filename", ""),
                        line=item.get("line_number", 0),
                        severity=severity,
                        confidence=item.get("issue_confidence", "LOW").upper(),
                        test_id=item.get("test_id", ""),
                        message=item.get("issue_text", ""),
                    )
                    findings.append(finding)
                    if severity in severity_counts:
                        severity_counts[severity] += 1
            except json.JSONDecodeError:
                pass

        # Check if gate should fail
        threshold = config.security.fail_on_severity
        findings_above_threshold = sum(
            1 for f in findings if _severity_meets_threshold(f.severity, threshold)
        )
        passed = findings_above_threshold <= config.security.max_findings

        recommendation = None
        if not passed:
            recommendation = (
                f"Fix {findings_above_threshold} security finding(s) "
                f"at or above {threshold} severity before AI review."
            )

        return SecurityGateResult(
            passed=passed,
            findings=findings,
            severity_counts=severity_counts,
            recommendation=recommendation,
        )

    except FileNotFoundError:
        return SecurityGateResult(
            passed=True,
            recommendation="Bandit not installed, skipping security scan.",
        )
