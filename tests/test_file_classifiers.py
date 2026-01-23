"""Tests for file-type aware routing."""

from pr_review_agent.analysis.file_classifiers import (
    classify_file,
    classify_files,
)


def test_classify_infrastructure_terraform():
    """Terraform files classified as infrastructure."""
    result = classify_file("infra/main.tf")

    assert result.domain == "infrastructure"
    assert "security" in result.focus_areas


def test_classify_infrastructure_dockerfile():
    """Dockerfiles classified as infrastructure."""
    result = classify_file("Dockerfile")

    assert result.domain == "infrastructure"


def test_classify_infrastructure_github_workflow():
    """GitHub workflow files classified as infrastructure."""
    result = classify_file(".github/workflows/ci.yml")

    assert result.domain == "infrastructure"


def test_classify_frontend_tsx():
    """TSX files classified as frontend."""
    result = classify_file("src/components/Button.tsx")

    assert result.domain == "frontend"
    assert "accessibility" in result.focus_areas


def test_classify_frontend_css():
    """CSS files classified as frontend."""
    result = classify_file("styles/main.css")

    assert result.domain == "frontend"


def test_classify_backend_python():
    """Python files classified as backend."""
    result = classify_file("src/app/handler.py")

    assert result.domain == "backend"
    assert "logic_errors" in result.focus_areas


def test_classify_backend_go():
    """Go files classified as backend."""
    result = classify_file("pkg/service/main.go")

    assert result.domain == "backend"


def test_classify_tests():
    """Test files classified as tests."""
    result = classify_file("tests/test_main.py")

    assert result.domain == "tests"
    assert "test_quality" in result.focus_areas


def test_classify_tests_spec():
    """Spec files classified as tests."""
    result = classify_file("src/utils.spec.ts")

    assert result.domain == "tests"


def test_classify_docs_markdown():
    """Markdown files classified as docs."""
    result = classify_file("docs/guide.md")

    assert result.domain == "docs"
    assert "accuracy" in result.focus_areas


def test_classify_config_toml():
    """TOML files classified as config."""
    result = classify_file("pyproject.toml")

    assert result.domain == "config"


def test_classify_unknown_defaults_to_backend():
    """Unknown file types default to backend."""
    result = classify_file("something/unknown.xyz")

    assert result.domain == "backend"


def test_classify_files_determines_dominant_domain():
    """Multiple files should identify the dominant domain."""
    files = [
        "src/handler.py",
        "src/utils.py",
        "src/models.py",
        "tests/test_handler.py",
    ]

    result = classify_files(files)

    assert result.dominant_domain == "backend"
    assert result.domain_counts.get("backend", 0) == 3
    assert result.domain_counts.get("tests", 0) == 1


def test_classify_files_combines_focus_areas():
    """Combined focus areas from all domains."""
    files = [
        "src/handler.py",         # backend: logic_errors, security, error_handling
        "tests/test_handler.py",  # tests: coverage_gaps, test_quality, assertions
    ]

    result = classify_files(files)

    assert "logic_errors" in result.combined_focus
    assert "test_quality" in result.combined_focus


def test_classify_files_empty_list():
    """Empty file list returns default routing."""
    result = classify_files([])

    assert result.dominant_domain == "backend"
    assert result.classifications == []
