"""Webhook notifications for low-confidence reviews."""

from dataclasses import dataclass

import requests

from pr_review_agent.config import EscalationConfig
from pr_review_agent.github_client import PRData
from pr_review_agent.review.confidence import ConfidenceResult


@dataclass
class EscalationPayload:
    """Payload sent to escalation webhook."""

    pr_url: str
    pr_title: str
    pr_author: str
    repo: str
    pr_number: int
    confidence_score: float
    confidence_level: str
    review_summary: str
    escalation_reason: str


def should_escalate(
    confidence: ConfidenceResult,
    config: EscalationConfig,
) -> bool:
    """Determine if a review should be escalated."""
    if not config.enabled:
        return False
    if not config.webhook_url:
        return False
    return confidence.score < config.trigger_below_confidence


def build_payload(
    pr: PRData,
    confidence: ConfidenceResult,
    review_summary: str,
) -> EscalationPayload:
    """Build the escalation payload."""
    reasons = []
    if confidence.level == "low":
        reasons.append(
            f"Confidence score ({confidence.score:.2f}) is below threshold"
        )
    for factor, value in confidence.factors.items():
        if value < -0.2:
            reasons.append(f"High penalty from {factor}: {value:.2f}")

    return EscalationPayload(
        pr_url=pr.url,
        pr_title=pr.title,
        pr_author=pr.author,
        repo=f"{pr.owner}/{pr.repo}",
        pr_number=pr.number,
        confidence_score=confidence.score,
        confidence_level=confidence.level,
        review_summary=review_summary,
        escalation_reason="; ".join(reasons) if reasons else "Low confidence",
    )


def _format_slack_payload(payload: EscalationPayload) -> dict:
    """Format payload as Slack incoming webhook message."""
    color = "#dc3545"  # red for low confidence
    if payload.confidence_score >= 0.3:
        color = "#ffc107"  # yellow for borderline

    return {
        "attachments": [
            {
                "color": color,
                "title": f"Review Escalation: {payload.repo}#{payload.pr_number}",
                "title_link": payload.pr_url,
                "fields": [
                    {
                        "title": "PR",
                        "value": payload.pr_title,
                        "short": False,
                    },
                    {
                        "title": "Author",
                        "value": payload.pr_author,
                        "short": True,
                    },
                    {
                        "title": "Confidence",
                        "value": f"{payload.confidence_score:.0%} "
                                 f"({payload.confidence_level})",
                        "short": True,
                    },
                    {
                        "title": "Reason",
                        "value": payload.escalation_reason,
                        "short": False,
                    },
                    {
                        "title": "Summary",
                        "value": payload.review_summary[:300],
                        "short": False,
                    },
                ],
                "footer": "PR Review Agent",
            }
        ]
    }


def _format_generic_payload(payload: EscalationPayload) -> dict:
    """Format payload as generic JSON webhook."""
    return {
        "event": "review_escalation",
        "pr_url": payload.pr_url,
        "pr_title": payload.pr_title,
        "pr_author": payload.pr_author,
        "repo": payload.repo,
        "pr_number": payload.pr_number,
        "confidence_score": payload.confidence_score,
        "confidence_level": payload.confidence_level,
        "review_summary": payload.review_summary,
        "escalation_reason": payload.escalation_reason,
    }


def send_webhook(
    payload: EscalationPayload,
    config: EscalationConfig,
) -> bool:
    """Send escalation webhook. Returns True on success."""
    if config.slack_format:
        body = _format_slack_payload(payload)
    else:
        body = _format_generic_payload(payload)

    try:
        response = requests.post(
            config.webhook_url,
            json=body,
            timeout=10,
        )
        return response.ok
    except requests.RequestException:
        return False
