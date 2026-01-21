"""Tests for config loading."""

from pathlib import Path

from pr_review_agent.config import load_config


def test_load_config_from_yaml(tmp_path: Path):
    """Test loading config from YAML file."""
    config_file = tmp_path / ".ai-review.yaml"
    config_file.write_text("""
version: 1
limits:
  max_lines_changed: 300
  max_files_changed: 10
linting:
  enabled: true
  fail_threshold: 5
llm:
  default_model: claude-sonnet-4-20250514
""")
    config = load_config(config_file)

    assert config.limits.max_lines_changed == 300
    assert config.limits.max_files_changed == 10
    assert config.linting.enabled is True
    assert config.linting.fail_threshold == 5
    assert config.llm.default_model == "claude-sonnet-4-20250514"


def test_load_config_defaults():
    """Test default config values when file doesn't exist."""
    config = load_config(Path("/nonexistent/.ai-review.yaml"))

    assert config.limits.max_lines_changed == 500
    assert config.limits.max_files_changed == 20
    assert config.linting.enabled is True
    assert config.llm.default_model == "claude-sonnet-4-20250514"


def test_config_ignore_patterns(tmp_path: Path):
    """Test ignore patterns are loaded correctly."""
    config_file = tmp_path / ".ai-review.yaml"
    config_file.write_text("""
version: 1
ignore:
  - "*.lock"
  - "*.md"
""")
    config = load_config(config_file)

    assert "*.lock" in config.ignore
    assert "*.md" in config.ignore
