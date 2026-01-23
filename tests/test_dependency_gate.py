"""Tests for dependency audit gate."""

from unittest.mock import patch

from pr_review_agent.gates.dependency_gate import (
    check_dependencies,
    parse_new_dependencies,
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
