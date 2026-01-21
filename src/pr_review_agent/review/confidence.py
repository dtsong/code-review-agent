"""Confidence scoring for review results."""

from dataclasses import dataclass, field

from pr_review_agent.config import Config
from pr_review_agent.github_client import PRData
from pr_review_agent.review.llm_reviewer import LLMReviewResult

SEVERITY_WEIGHTS = {
    "critical": 0.6,
    "major": 0.3,
    "minor": 0.1,
    "suggestion": 0.25,
}


@dataclass
class ConfidenceResult:
    """Confidence scoring result."""

    score: float
    level: str
    factors: dict[str, float] = field(default_factory=dict)
    recommendation: str = ""


def calculate_confidence(
    review: LLMReviewResult,
    pr: PRData,
    config: Config,
) -> ConfidenceResult:
    """Calculate confidence score based on review results."""
    # Start with base score
    score = 1.0
    factors = {}

    # Deduct for issues by severity
    issue_penalty = 0.0
    for issue in review.issues:
        penalty = SEVERITY_WEIGHTS.get(issue.severity, 0.05)
        issue_penalty += penalty

    score -= issue_penalty
    factors["issues"] = -issue_penalty

    # Bonus for having strengths mentioned
    if review.strengths:
        strength_bonus = min(0.1, len(review.strengths) * 0.03)
        score += strength_bonus
        factors["strengths"] = strength_bonus

    # Penalty for concerns
    if review.concerns:
        concern_penalty = min(0.2, len(review.concerns) * 0.05)
        score -= concern_penalty
        factors["concerns"] = -concern_penalty

    # Penalty for questions (uncertainty)
    if review.questions:
        question_penalty = min(0.15, len(review.questions) * 0.05)
        score -= question_penalty
        factors["questions"] = -question_penalty

    # Clamp to valid range
    score = max(0.0, min(1.0, score))

    # Determine level and recommendation
    high_threshold = config.confidence.high
    low_threshold = config.confidence.low

    if score >= high_threshold:
        level = "high"
        recommendation = "auto_approve"
    elif score >= low_threshold:
        level = "medium"
        recommendation = "comment_only"
    else:
        level = "low"
        recommendation = "request_human_review"

    return ConfidenceResult(
        score=score,
        level=level,
        factors=factors,
        recommendation=recommendation,
    )
