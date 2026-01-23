"""Dependency audit gate to detect vulnerable or deprecated packages."""

import json
import re
import subprocess
from dataclasses import dataclass, field


@dataclass
class VulnerableDep:
    """A dependency with known vulnerabilities."""

    name: str
    version: str
    advisory: str
    severity: str  # "low", "medium", "high", "critical"


@dataclass
class DependencyGateResult:
    """Result of dependency audit gate."""

    passed: bool
    new_deps: list[str] = field(default_factory=list)
    vulnerable_deps: list[VulnerableDep] = field(default_factory=list)
    deprecated_deps: list[str] = field(default_factory=list)
    reason: str | None = None
    recommendation: str | None = None


def parse_new_dependencies(diff: str) -> list[str]:
    """Extract newly added dependencies from diff of pyproject.toml or requirements.txt.

    Looks for added lines (+) containing package specs.
    """
    new_deps = []
    in_deps_section = False

    for line in diff.split("\n"):
        # Track if we're in a dependencies section (pyproject.toml)
        if "[project.dependencies]" in line or "[dependencies]" in line:
            in_deps_section = True
            continue
        if line.startswith("[") and "dependencies" not in line.lower():
            in_deps_section = False
            continue

        # Look for added lines with package-like content
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:].strip()
            # Skip empty, comments, section headers
            if not content or content.startswith("#") or content.startswith("["):
                continue

            # Match package specs: "package>=1.0" or "package==1.0" or just "package"
            # In pyproject.toml deps are quoted strings in a list
            # In requirements.txt they're bare package specs
            match = re.match(
                r'["\']?\s*([a-zA-Z0-9_-]+)\s*(?:[><=!~]+\s*[\d.]+)?',
                content,
            )
            if match and in_deps_section:
                dep_name = match.group(1)
                if dep_name not in ("python", "requires-python"):
                    new_deps.append(dep_name)

            # requirements.txt format (no section headers)
            if not in_deps_section and re.match(r'^[a-zA-Z0-9_-]+\s*[><=!~]', content):
                match = re.match(r'^([a-zA-Z0-9_-]+)', content)
                if match:
                    new_deps.append(match.group(1))

    return list(set(new_deps))


def run_pip_audit() -> list[VulnerableDep]:
    """Run pip-audit to check for known vulnerabilities."""
    try:
        result = subprocess.run(
            ["pip-audit", "--format=json", "--progress-spinner=off"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if not result.stdout:
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        vulnerabilities = []
        # pip-audit JSON format: {"dependencies": [...]}
        deps = data if isinstance(data, list) else data.get("dependencies", [])
        for dep in deps:
            vulns = dep.get("vulns", [])
            for vuln in vulns:
                vulnerabilities.append(VulnerableDep(
                    name=dep.get("name", ""),
                    version=dep.get("version", ""),
                    advisory=vuln.get("id", ""),
                    severity=(
                        vuln.get("fix_versions", [""])[0]
                        if vuln.get("fix_versions")
                        else "unknown"
                    ),
                ))

        return vulnerabilities

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def check_dependencies(
    diff: str,
    block_vulnerable: bool = True,
    block_deprecated: bool = False,
) -> DependencyGateResult:
    """Check for vulnerable or problematic new dependencies.

    Args:
        diff: The unified diff string (should include pyproject.toml/requirements.txt changes).
        block_vulnerable: Whether to fail gate on vulnerable deps.
        block_deprecated: Whether to fail gate on deprecated deps.
    """
    # Parse new deps from diff
    new_deps = parse_new_dependencies(diff)

    if not new_deps:
        return DependencyGateResult(passed=True, new_deps=[])

    # Run vulnerability scan
    vulnerable = run_pip_audit()

    # Filter to only vulnerabilities in new deps
    relevant_vulns = [v for v in vulnerable if v.name in new_deps]

    # Determine pass/fail
    passed = True
    reason = None
    recommendation = None

    if block_vulnerable and relevant_vulns:
        passed = False
        vuln_names = ", ".join(set(v.name for v in relevant_vulns))
        reason = f"New dependencies have known vulnerabilities: {vuln_names}"
        recommendation = "Update to patched versions or choose alternative packages."

    return DependencyGateResult(
        passed=passed,
        new_deps=new_deps,
        vulnerable_deps=relevant_vulns,
        deprecated_deps=[],
        reason=reason,
        recommendation=recommendation,
    )
