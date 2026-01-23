"""File-type aware routing for review focus."""

import fnmatch
from dataclasses import dataclass, field

from pr_review_agent.config import Config

# Default routing rules - maps domain to file patterns and focus areas
DEFAULT_FILE_ROUTING: dict[str, dict] = {
    "infrastructure": {
        "patterns": [
            "*.tf", "*.tfvars", "Dockerfile", "docker-compose.*",
            ".github/workflows/*", "*.yml", "*.yaml",
            "Makefile", "*.sh",
        ],
        "focus": ["security", "idempotency", "secrets_exposure"],
    },
    "frontend": {
        "patterns": [
            "*.tsx", "*.jsx", "*.css", "*.scss", "*.vue",
            "*.svelte", "*.html",
        ],
        "focus": ["accessibility", "performance", "xss"],
    },
    "backend": {
        "patterns": ["*.py", "*.go", "*.rs", "*.java", "*.rb"],
        "focus": ["logic_errors", "security", "error_handling"],
    },
    "tests": {
        "patterns": [
            "test_*", "*_test.*", "*.spec.*", "tests/*",
            "**/test/**", "conftest.py",
        ],
        "focus": ["coverage_gaps", "test_quality", "assertions"],
    },
    "docs": {
        "patterns": ["*.md", "*.rst", "*.txt", "docs/*", "README*"],
        "focus": ["accuracy", "completeness", "clarity"],
    },
    "config": {
        "patterns": [
            "*.toml", "*.ini", "*.cfg", "*.env*",
            "pyproject.toml", "package.json", "tsconfig.json",
        ],
        "focus": ["security_implications", "environment_consistency"],
    },
}


@dataclass
class FileClassification:
    """Classification of a single file."""

    path: str
    domain: str
    focus_areas: list[str] = field(default_factory=list)


@dataclass
class RoutingResult:
    """Result of file-type routing analysis."""

    classifications: list[FileClassification] = field(default_factory=list)
    dominant_domain: str = "backend"
    combined_focus: list[str] = field(default_factory=list)
    domain_counts: dict[str, int] = field(default_factory=dict)


def classify_file(path: str, routing_rules: dict | None = None) -> FileClassification:
    """Classify a single file by its path into a domain.

    Args:
        path: File path relative to repo root.
        routing_rules: Optional custom routing rules. Defaults to DEFAULT_FILE_ROUTING.

    Priority order: tests > docs > infrastructure > config > frontend > backend
    """
    rules = routing_rules or DEFAULT_FILE_ROUTING

    # Check in priority order: more specific domains first
    priority_order = ["tests", "docs", "infrastructure", "config", "frontend", "backend"]

    for domain in priority_order:
        if domain not in rules:
            continue
        domain_config = rules[domain]
        patterns = domain_config.get("patterns", [])
        for pattern in patterns:
            # Match against full path and basename
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(
                path.split("/")[-1], pattern
            ):
                return FileClassification(
                    path=path,
                    domain=domain,
                    focus_areas=domain_config.get("focus", []),
                )

    # Default to backend for unmatched files
    return FileClassification(
        path=path,
        domain="backend",
        focus_areas=DEFAULT_FILE_ROUTING["backend"]["focus"],
    )


def classify_files(
    files: list[str],
    config: Config | None = None,
) -> RoutingResult:
    """Classify all changed files and determine routing.

    Args:
        files: List of changed file paths.
        config: Optional config with custom file_routing rules.
    """
    routing_rules = None
    if config and hasattr(config, "file_routing"):
        routing_rules = config.file_routing

    classifications = [classify_file(f, routing_rules) for f in files]

    # Count domains
    domain_counts: dict[str, int] = {}
    for c in classifications:
        domain_counts[c.domain] = domain_counts.get(c.domain, 0) + 1

    # Determine dominant domain
    dominant = max(domain_counts, key=domain_counts.get) if domain_counts else "backend"

    # Combine focus areas (unique, ordered by frequency)
    focus_count: dict[str, int] = {}
    for c in classifications:
        for area in c.focus_areas:
            focus_count[area] = focus_count.get(area, 0) + 1

    combined_focus = sorted(focus_count.keys(), key=lambda x: -focus_count[x])

    return RoutingResult(
        classifications=classifications,
        dominant_domain=dominant,
        combined_focus=combined_focus,
        domain_counts=domain_counts,
    )
