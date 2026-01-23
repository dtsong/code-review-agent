"""Tests for escalation webhook notifications."""

from unittest.mock import MagicMock, patch

from pr_review_agent.config import EscalationConfig
from pr_review_agent.escalation.webhook import (
    EscalationPayload,
    _format_generic_payload,
    _format_slack_payload,
    build_payload,
    send_webhook,
    should_escalate,
)
from pr_review_agent.github_client import PRData
from pr_review_agent.review.confidence import ConfidenceResult


def _make_pr() -> PRData:
    return PRData(
        owner="testorg",
        repo="testrepo",
        number=42,
        title="Fix auth bug",
        author="dev1",
        description="Fixes login issue",
        diff="+ fix",
        files_changed=["src/auth.py"],
        lines_added=10,
        lines_removed=5,
        base_branch="main",
        head_branch="fix/auth",
        url="https://github.com/testorg/testrepo/pull/42",
    )


def _make_confidence(score: float, level: str) -> ConfidenceResult:
    return ConfidenceResult(
        score=score,
        level=level,
        factors={"issues": -0.5, "concerns": -0.1},
        recommendation="request_human_review",
    )


class TestShouldEscalate:
    def test_escalates_when_below_threshold(self):
        config = EscalationConfig(
            enabled=True,
            webhook_url="https://hooks.slack.com/test",
            trigger_below_confidence=0.5,
        )
        confidence = _make_confidence(0.3, "low")
        assert should_escalate(confidence, config) is True

    def test_no_escalation_when_above_threshold(self):
        config = EscalationConfig(
            enabled=True,
            webhook_url="https://hooks.slack.com/test",
            trigger_below_confidence=0.5,
        )
        confidence = _make_confidence(0.7, "medium")
        assert should_escalate(confidence, config) is False

    def test_no_escalation_when_disabled(self):
        config = EscalationConfig(
            enabled=False,
            webhook_url="https://hooks.slack.com/test",
            trigger_below_confidence=0.5,
        )
        confidence = _make_confidence(0.3, "low")
        assert should_escalate(confidence, config) is False

    def test_no_escalation_when_no_url(self):
        config = EscalationConfig(
            enabled=True,
            webhook_url="",
            trigger_below_confidence=0.5,
        )
        confidence = _make_confidence(0.3, "low")
        assert should_escalate(confidence, config) is False

    def test_escalation_at_exact_threshold(self):
        config = EscalationConfig(
            enabled=True,
            webhook_url="https://hooks.slack.com/test",
            trigger_below_confidence=0.5,
        )
        confidence = _make_confidence(0.5, "medium")
        assert should_escalate(confidence, config) is False


class TestBuildPayload:
    def test_builds_complete_payload(self):
        pr = _make_pr()
        confidence = _make_confidence(0.3, "low")
        payload = build_payload(pr, confidence, "Issues found in auth")

        assert payload.pr_url == pr.url
        assert payload.pr_title == pr.title
        assert payload.pr_author == pr.author
        assert payload.repo == "testorg/testrepo"
        assert payload.pr_number == 42
        assert payload.confidence_score == 0.3
        assert payload.confidence_level == "low"
        assert payload.review_summary == "Issues found in auth"
        assert "below threshold" in payload.escalation_reason

    def test_includes_high_penalty_factors(self):
        pr = _make_pr()
        confidence = ConfidenceResult(
            score=0.2,
            level="low",
            factors={"issues": -0.6, "concerns": -0.3},
            recommendation="request_human_review",
        )
        payload = build_payload(pr, confidence, "Summary")

        assert "issues" in payload.escalation_reason
        assert "concerns" in payload.escalation_reason


class TestFormatSlackPayload:
    def test_slack_format_structure(self):
        payload = EscalationPayload(
            pr_url="https://github.com/org/repo/pull/1",
            pr_title="Test PR",
            pr_author="dev",
            repo="org/repo",
            pr_number=1,
            confidence_score=0.2,
            confidence_level="low",
            review_summary="Issues found",
            escalation_reason="Low confidence",
        )
        result = _format_slack_payload(payload)

        assert "attachments" in result
        attachment = result["attachments"][0]
        assert attachment["color"] == "#dc3545"
        assert "Escalation" in attachment["title"]
        assert len(attachment["fields"]) == 5

    def test_slack_yellow_for_borderline(self):
        payload = EscalationPayload(
            pr_url="url",
            pr_title="PR",
            pr_author="dev",
            repo="org/repo",
            pr_number=1,
            confidence_score=0.4,
            confidence_level="low",
            review_summary="Summary",
            escalation_reason="Reason",
        )
        result = _format_slack_payload(payload)
        assert result["attachments"][0]["color"] == "#ffc107"


class TestFormatGenericPayload:
    def test_generic_format_structure(self):
        payload = EscalationPayload(
            pr_url="https://github.com/org/repo/pull/1",
            pr_title="Test PR",
            pr_author="dev",
            repo="org/repo",
            pr_number=1,
            confidence_score=0.3,
            confidence_level="low",
            review_summary="Issues found",
            escalation_reason="Low confidence",
        )
        result = _format_generic_payload(payload)

        assert result["event"] == "review_escalation"
        assert result["pr_url"] == payload.pr_url
        assert result["confidence_score"] == 0.3


class TestSendWebhook:
    @patch("pr_review_agent.escalation.webhook.requests.post")
    def test_sends_slack_webhook(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        config = EscalationConfig(
            enabled=True,
            webhook_url="https://hooks.slack.com/services/T/B/X",
            slack_format=True,
        )
        payload = EscalationPayload(
            pr_url="url",
            pr_title="PR",
            pr_author="dev",
            repo="org/repo",
            pr_number=1,
            confidence_score=0.3,
            confidence_level="low",
            review_summary="Summary",
            escalation_reason="Reason",
        )

        result = send_webhook(payload, config)

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "attachments" in call_kwargs.kwargs["json"]

    @patch("pr_review_agent.escalation.webhook.requests.post")
    def test_sends_generic_webhook(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        config = EscalationConfig(
            enabled=True,
            webhook_url="https://example.com/webhook",
            slack_format=False,
        )
        payload = EscalationPayload(
            pr_url="url",
            pr_title="PR",
            pr_author="dev",
            repo="org/repo",
            pr_number=1,
            confidence_score=0.3,
            confidence_level="low",
            review_summary="Summary",
            escalation_reason="Reason",
        )

        result = send_webhook(payload, config)

        assert result is True
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["json"]["event"] == "review_escalation"

    @patch("pr_review_agent.escalation.webhook.requests.post")
    def test_returns_false_on_http_error(self, mock_post):
        mock_post.return_value = MagicMock(ok=False, status_code=500)
        config = EscalationConfig(
            enabled=True,
            webhook_url="https://hooks.slack.com/test",
        )
        payload = EscalationPayload(
            pr_url="url",
            pr_title="PR",
            pr_author="dev",
            repo="org/repo",
            pr_number=1,
            confidence_score=0.3,
            confidence_level="low",
            review_summary="Summary",
            escalation_reason="Reason",
        )

        assert send_webhook(payload, config) is False

    @patch("pr_review_agent.escalation.webhook.requests.post")
    def test_returns_false_on_network_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.ConnectionError("timeout")
        config = EscalationConfig(
            enabled=True,
            webhook_url="https://hooks.slack.com/test",
        )
        payload = EscalationPayload(
            pr_url="url",
            pr_title="PR",
            pr_author="dev",
            repo="org/repo",
            pr_number=1,
            confidence_score=0.3,
            confidence_level="low",
            review_summary="Summary",
            escalation_reason="Reason",
        )

        assert send_webhook(payload, config) is False
