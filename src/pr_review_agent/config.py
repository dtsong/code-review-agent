"""Configuration loading for PR Review Agent."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LimitsConfig:
    """Size limits configuration."""

    max_lines_changed: int = 500
    max_files_changed: int = 20


@dataclass
class LintingConfig:
    """Linting configuration."""

    enabled: bool = True
    tool: str = "ruff"
    fail_on_error: bool = True
    fail_threshold: int = 10


@dataclass
class SecurityConfig:
    """Security scanning configuration."""

    enabled: bool = True
    tool: str = "bandit"
    fail_on_severity: str = "high"  # critical, high, medium, low
    max_findings: int = 5


@dataclass
class LLMConfig:
    """LLM configuration."""

    provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-20250514"
    simple_model: str = "claude-haiku-4-5-20251001"
    simple_threshold_lines: int = 50
    max_tokens: int = 4096


@dataclass
class ConfidenceConfig:
    """Confidence threshold configuration."""

    high: float = 0.8
    low: float = 0.5


@dataclass
class Config:
    """Main configuration object."""

    version: int = 1
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    linting: LintingConfig = field(default_factory=LintingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    ignore: list[str] = field(default_factory=list)
    review_focus: list[str] = field(default_factory=list)


def load_config(path: Path) -> Config:
    """Load configuration from YAML file, with defaults for missing values."""
    config = Config()

    if not path.exists():
        return config

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    if "limits" in data:
        config.limits = LimitsConfig(**data["limits"])

    if "linting" in data:
        config.linting = LintingConfig(**{
            k: v for k, v in data["linting"].items()
            if k in LintingConfig.__dataclass_fields__
        })

    if "security" in data:
        config.security = SecurityConfig(**{
            k: v for k, v in data["security"].items()
            if k in SecurityConfig.__dataclass_fields__
        })

    if "llm" in data:
        config.llm = LLMConfig(**{
            k: v for k, v in data["llm"].items()
            if k in LLMConfig.__dataclass_fields__
        })

    if "confidence" in data:
        config.confidence = ConfidenceConfig(**data["confidence"])

    if "ignore" in data:
        config.ignore = data["ignore"]

    if "review_focus" in data:
        config.review_focus = data["review_focus"]

    return config
