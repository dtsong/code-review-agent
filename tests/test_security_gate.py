"""Tests for security gate."""

from unittest.mock import patch

from pr_review_agent.config import Config, SecurityConfig
from pr_review_agent.gates.security_gate import (
    SecurityFinding,
    SecurityGateResult,
    run_security_scan,
)


def test_security_gate_disabled():
    """Disabled security gate should always pass."""
    config = Config(security=SecurityConfig(enabled=False))

    result = run_security_scan(["some_file.py"], config)

    assert result.passed is True
    assert result.findings == []


def test_security_gate_no_files():
    """No files should pass."""
    config = Config(security=SecurityConfig(enabled=True))

    result = run_security_scan([], config)

    assert result.passed is True


def test_security_gate_no_python_files():
    """Non-Python files should pass."""
    config = Config(security=SecurityConfig(enabled=True))

    result = run_security_scan(["readme.md", "config.yaml"], config)

    assert result.passed is True


def test_security_gate_clean_files(tmp_path):
    """Clean files should pass security gate."""
    test_file = tmp_path / "clean.py"
    test_file.write_text('def hello():\n    return "world"\n')

    config = Config(security=SecurityConfig(enabled=True))

    result = run_security_scan([str(test_file)], config)

    assert result.passed is True
    assert result.findings == []


def test_security_gate_detects_issues(tmp_path):
    """Files with security issues should be detected."""
    test_file = tmp_path / "insecure.py"
    test_file.write_text(
        'import subprocess\n'
        'def run(cmd):\n'
        '    subprocess.call(cmd, shell=True)\n'
    )

    config = Config(security=SecurityConfig(enabled=True, max_findings=0))

    result = run_security_scan([str(test_file)], config)

    assert result.passed is False
    assert len(result.findings) >= 1
    assert result.severity_counts["HIGH"] >= 1 or result.severity_counts["MEDIUM"] >= 1


def test_security_gate_respects_max_findings(tmp_path):
    """Gate should pass if findings under max_findings threshold."""
    test_file = tmp_path / "minor.py"
    test_file.write_text(
        'import subprocess\n'
        'def run(cmd):\n'
        '    subprocess.call(cmd, shell=True)\n'
    )

    config = Config(security=SecurityConfig(enabled=True, max_findings=50))

    result = run_security_scan([str(test_file)], config)

    # Should pass because findings < max_findings
    assert result.passed is True


def test_security_gate_fail_on_severity(tmp_path):
    """Gate should fail based on severity threshold."""
    test_file = tmp_path / "high_sev.py"
    test_file.write_text(
        'import subprocess\n'
        'def run(cmd):\n'
        '    subprocess.call(cmd, shell=True)\n'
    )

    # Only fail on critical - high severity should pass
    config = Config(security=SecurityConfig(
        enabled=True, fail_on_severity="critical", max_findings=50
    ))

    result = run_security_scan([str(test_file)], config)

    # Should pass because we only fail on critical, and this is high/medium
    assert result.passed is True


def test_security_gate_bandit_not_installed():
    """Missing bandit should pass with recommendation."""
    config = Config(security=SecurityConfig(enabled=True))

    with patch("pr_review_agent.gates.security_gate.subprocess.run", side_effect=FileNotFoundError):
        result = run_security_scan(["file.py"], config)

    assert result.passed is True
    assert result.recommendation is not None
    assert "bandit" in result.recommendation.lower()


def test_security_finding_dataclass():
    """SecurityFinding should store finding details."""
    finding = SecurityFinding(
        file="test.py",
        line=10,
        severity="HIGH",
        confidence="HIGH",
        test_id="B602",
        message="subprocess call with shell=True",
    )
    assert finding.file == "test.py"
    assert finding.severity == "HIGH"


def test_security_gate_result_structure():
    """SecurityGateResult should have correct structure."""
    result = SecurityGateResult(
        passed=False,
        findings=[],
        severity_counts={"CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 0},
        recommendation="Fix security issues.",
    )
    assert result.passed is False
    assert result.severity_counts["HIGH"] == 1
