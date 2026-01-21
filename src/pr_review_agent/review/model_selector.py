"""Model selection based on PR characteristics."""

from pr_review_agent.config import Config
from pr_review_agent.github_client import PRData


def select_model(pr: PRData, config: Config) -> str:
    """Select appropriate model based on PR size.

    Small PRs use the cheaper/faster model.
    Larger PRs use the more capable model.
    """
    total_lines = pr.lines_added + pr.lines_removed

    if total_lines < config.llm.simple_threshold_lines:
        return config.llm.simple_model

    return config.llm.default_model
