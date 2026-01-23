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
class LLMConfig:
    """LLM configuration."""

    provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-20250514"
    simple_model: str = "claude-haiku-4-5-20251001"
    simple_threshold_lines: int = 50
    max_tokens: int = 4096


@dataclass
class CoverageConfig:
    """Coverage gate configuration."""

    enabled: bool = True
    min_coverage: float = 80.0
    fail_on_decrease: bool = True
    report_path: str = "coverage.xml"


@dataclass
class DependencyConfig:
    """Dependency audit gate configuration."""

    enabled: bool = True
    block_vulnerable: bool = True
    block_deprecated: bool = False
    allowed_licenses: list[str] = field(
        default_factory=lambda: ["MIT", "Apache-2.0", "BSD-3-Clause"]
    )


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
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    dependencies: DependencyConfig = field(default_factory=DependencyConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    file_routing: dict | None = None
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

    if "llm" in data:
        config.llm = LLMConfig(**{
            k: v for k, v in data["llm"].items()
            if k in LLMConfig.__dataclass_fields__
        })

    if "coverage" in data:
        config.coverage = CoverageConfig(**{
            k: v for k, v in data["coverage"].items()
            if k in CoverageConfig.__dataclass_fields__
        })

    if "dependencies" in data:
        config.dependencies = DependencyConfig(**{
            k: v for k, v in data["dependencies"].items()
            if k in DependencyConfig.__dataclass_fields__
        })

    if "confidence" in data:
        config.confidence = ConfidenceConfig(**data["confidence"])

    if "file_routing" in data:
        config.file_routing = data["file_routing"]

    if "ignore" in data:
        config.ignore = data["ignore"]

    if "review_focus" in data:
        config.review_focus = data["review_focus"]

    return config
