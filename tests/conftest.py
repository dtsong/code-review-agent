"""Shared test fixtures and configuration."""

import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock


@dataclass
class MockPRData:
    """Mock PR data for testing."""

    number: int = 1
    repo: str = "owner/repo"
    owner: str = "owner"
    author: str = "testuser"
    title: str = "Test PR"
    description: str = ""
    files_changed: list = None
    lines_changed: int = 50
    lines_added: int = 30
    lines_removed: int = 20
    diff: str = ""
    base_branch: str = "main"
    head_branch: str = "feature"
    url: str = "https://github.com/owner/repo/pull/1"

    def __post_init__(self):
        if self.files_changed is None:
            self.files_changed = ["src/main.py"]


@dataclass
class MockConfig:
    """Mock configuration for testing."""

    max_lines_changed: int = 500
    max_files_changed: int = 20
    lint_fail_threshold: int = 10
    simple_threshold_lines: int = 50
    default_model: str = "claude-sonnet-4-20250514"
    simple_model: str = "claude-haiku-4-5-20251001"


@pytest.fixture
def mock_pr():
    """Default mock PR."""
    return MockPRData()


@pytest.fixture
def mock_config():
    """Default mock config."""
    return MockConfig()


@pytest.fixture
def mock_anthropic_success():
    """Mock successful Anthropic API response."""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text="""{
        "summary": "Test review summary",
        "issues": [],
        "strengths": ["Clean code"],
        "concerns": [],
        "questions": []
    }"""
        )
    ]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    return mock_response
