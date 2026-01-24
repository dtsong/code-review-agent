"""Tests for dependency audit gate."""

import json
import subprocess
from unittest.mock import MagicMock, patch

from pr_review_agent.gates.dependency_gate import (
    check_dependencies,
    parse_new_dependencies,
    run_pip_audit,
)

PYPROJECT_DIFF = """\
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -10,6 +10,8 @@ dependencies = [
     "pyyaml>=6.0",
     "requests>=2.31.0",
+    "flask>=3.0.0",
+    "celery>=5.3.0",
 ]
"""

REQUIREMENTS_DIFF = """\
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,5 @@
 requests>=2.31.0
+django>=4.2.0
+redis>=5.0.0
"""


def test_parse_new_deps_pyproject():
    """Parse new dependencies from pyproject.toml diff."""
    # Need section header for pyproject format
    diff_with_section = """\
+[project.dependencies]
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -10,6 +10,8 @@
[project.dependencies]
     "pyyaml>=6.0",
     "requests>=2.31.0",
+    "flask>=3.0.0",
+    "celery>=5.3.0",
 ]
"""
    deps = parse_new_dependencies(diff_with_section)

    assert "flask" in deps
    assert "celery" in deps


def test_parse_new_deps_requirements_txt():
    """Parse new dependencies from requirements.txt diff."""
    deps = parse_new_dependencies(REQUIREMENTS_DIFF)

    assert "django" in deps
    assert "redis" in deps


def test_parse_new_deps_empty_diff():
    """Empty diff returns no new deps."""
    deps = parse_new_dependencies("")

    assert deps == []


def test_check_dependencies_no_new_deps():
    """No new deps means gate passes."""
    result = check_dependencies(diff="no dependency changes here")

    assert result.passed is True
    assert result.new_deps == []


@patch("pr_review_agent.gates.dependency_gate.run_pip_audit")
def test_check_dependencies_no_vulnerabilities(mock_audit):
    """New deps with no vulnerabilities pass."""
    mock_audit.return_value = []

    diff = """\
[project.dependencies]
+    "newpackage>=1.0.0",
"""
    result = check_dependencies(diff=diff, block_vulnerable=True)

    assert result.passed is True


@patch("pr_review_agent.gates.dependency_gate.run_pip_audit")
def test_check_dependencies_with_vulnerability(mock_audit):
    """Vulnerable new dep fails gate when block_vulnerable=True."""
    from pr_review_agent.gates.dependency_gate import VulnerableDep

    mock_audit.return_value = [
        VulnerableDep(
            name="newpackage",
            version="1.0.0",
            advisory="CVE-2024-1234",
            severity="high",
        )
    ]

    diff = """\
[project.dependencies]
+    "newpackage>=1.0.0",
"""
    result = check_dependencies(diff=diff, block_vulnerable=True)

    assert result.passed is False
    assert len(result.vulnerable_deps) == 1
    assert "vulnerabilities" in result.reason


@patch("pr_review_agent.gates.dependency_gate.run_pip_audit")
def test_check_dependencies_vulnerability_not_blocking(mock_audit):
    """Vulnerable dep passes when block_vulnerable=False."""
    from pr_review_agent.gates.dependency_gate import VulnerableDep

    mock_audit.return_value = [
        VulnerableDep(
            name="newpackage",
            version="1.0.0",
            advisory="CVE-2024-1234",
            severity="high",
        )
    ]

    diff = """\
[project.dependencies]
+    "newpackage>=1.0.0",
"""
    result = check_dependencies(diff=diff, block_vulnerable=False)

    assert result.passed is True


# --- parse_new_dependencies edge cases ---


def test_parse_new_deps_skips_comments_and_empty():
    """Comments and empty lines in added content are skipped."""
    diff = """\
[project.dependencies]
+    # This is a comment
+
+    "real-package>=1.0.0",
"""
    deps = parse_new_dependencies(diff)

    assert "real-package" in deps
    assert len(deps) == 1


def test_parse_new_deps_bare_requirements():
    """Bare requirements.txt format (no section header) with version specs."""
    diff = """\
+numpy>=1.24.0
+pandas==2.0.0
+scipy~=1.11
"""
    deps = parse_new_dependencies(diff)

    assert "numpy" in deps
    assert "pandas" in deps
    assert "scipy" in deps


# --- run_pip_audit tests ---


@patch("pr_review_agent.gates.dependency_gate.subprocess.run")
def test_run_pip_audit_with_vulnerabilities(mock_run):
    """Parses pip-audit JSON output into VulnerableDep list."""
    audit_output = json.dumps({
        "dependencies": [
            {
                "name": "requests",
                "version": "2.25.0",
                "vulns": [
                    {"id": "CVE-2023-1234", "fix_versions": ["2.31.0"]}
                ],
            }
        ]
    })
    mock_run.return_value = MagicMock(stdout=audit_output, returncode=0)

    result = run_pip_audit()

    assert len(result) == 1
    assert result[0].name == "requests"
    assert result[0].advisory == "CVE-2023-1234"


@patch("pr_review_agent.gates.dependency_gate.subprocess.run")
def test_run_pip_audit_empty(mock_run):
    """Empty stdout returns empty list."""
    mock_run.return_value = MagicMock(stdout="", returncode=0)

    result = run_pip_audit()

    assert result == []


@patch("pr_review_agent.gates.dependency_gate.subprocess.run")
def test_run_pip_audit_invalid_json(mock_run):
    """Malformed JSON returns empty list."""
    mock_run.return_value = MagicMock(stdout="not json{{{", returncode=0)

    result = run_pip_audit()

    assert result == []


@patch("pr_review_agent.gates.dependency_gate.subprocess.run")
def test_run_pip_audit_not_installed(mock_run):
    """FileNotFoundError (pip-audit not installed) returns empty list."""
    mock_run.side_effect = FileNotFoundError("pip-audit not found")

    result = run_pip_audit()

    assert result == []


@patch("pr_review_agent.gates.dependency_gate.subprocess.run")
def test_run_pip_audit_timeout(mock_run):
    """TimeoutExpired returns empty list."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip-audit", timeout=120)

    result = run_pip_audit()

    assert result == []
