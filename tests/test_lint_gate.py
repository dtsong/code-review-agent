"""Tests for lint gate."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from pr_review_agent.config import Config, LintingConfig
from pr_review_agent.gates.lint_gate import run_lint


def test_lint_gate_passes_clean_files(tmp_path: Path):
    """Clean files should pass lint gate."""
    # Create a clean Python file
    test_file = tmp_path / "clean.py"
    test_file.write_text('def hello():\n    return "world"\n')

    config = Config(linting=LintingConfig(enabled=True, fail_threshold=10))

    result = run_lint([str(test_file)], config)

    assert result.passed is True
    assert result.error_count == 0


def test_lint_gate_disabled():
    """Disabled lint gate should always pass."""
    config = Config(linting=LintingConfig(enabled=False))

    result = run_lint(["nonexistent.py"], config)

    assert result.passed is True
    assert result.issues == []


def test_lint_gate_fails_with_errors(tmp_path: Path):
    """Files with lint errors should fail gate."""
    # Create file with lint errors
    test_file = tmp_path / "bad.py"
    test_file.write_text('import os\nimport sys\nx=1\n')  # unused imports, spacing

    config = Config(linting=LintingConfig(enabled=True, fail_threshold=1))

    result = run_lint([str(test_file)], config)

    assert result.passed is False
    assert result.error_count >= 1
    assert len(result.issues) >= 1


def test_lint_gate_threshold(tmp_path: Path):
    """Gate should pass if errors under threshold."""
    test_file = tmp_path / "minor.py"
    test_file.write_text('import os\nx = 1\n')  # One unused import

    config = Config(linting=LintingConfig(enabled=True, fail_threshold=5))

    result = run_lint([str(test_file)], config)

    # Should pass because errors < threshold
    assert result.passed is True


def test_lint_gate_empty_files_list():
    """Empty files list should pass immediately."""
    config = Config(linting=LintingConfig(enabled=True, fail_threshold=1))

    result = run_lint([], config)

    assert result.passed is True
    assert result.issues == []
    assert result.error_count == 0


def test_lint_gate_no_python_files():
    """List with no Python files should pass."""
    config = Config(linting=LintingConfig(enabled=True, fail_threshold=1))

    result = run_lint(["file.js", "file.ts", "README.md"], config)

    assert result.passed is True
    assert result.issues == []


def test_lint_gate_ruff_invalid_json(tmp_path: Path):
    """Ruff outputting invalid JSON should be handled gracefully."""
    test_file = tmp_path / "test.py"
    test_file.write_text('x = 1\n')

    config = Config(linting=LintingConfig(enabled=True, fail_threshold=1))

    # Mock subprocess to return invalid JSON
    mock_result = MagicMock()
    mock_result.stdout = "not valid json {"
    mock_result.returncode = 0

    with patch("pr_review_agent.gates.lint_gate.subprocess.run", return_value=mock_result):
        result = run_lint([str(test_file)], config)

    # Should pass since we couldn't parse the errors
    assert result.passed is True
    assert result.issues == []
    assert result.error_count == 0


def test_lint_gate_ruff_not_installed():
    """FileNotFoundError (ruff not installed) should return PASS with recommendation."""
    config = Config(linting=LintingConfig(enabled=True, fail_threshold=1))

    with patch(
        "pr_review_agent.gates.lint_gate.subprocess.run",
        side_effect=FileNotFoundError("ruff not found"),
    ):
        result = run_lint(["file.py"], config)

    assert result.passed is True
    assert result.recommendation == "Ruff not installed, skipping lint check."
