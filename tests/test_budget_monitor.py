"""Tests for budget monitoring."""

from unittest.mock import MagicMock, patch

from pr_review_agent.config import BudgetConfig
from pr_review_agent.metrics.budget_monitor import (
    BudgetStatus,
    check_budget,
    get_monthly_spend,
    send_budget_alert,
    should_pause_review,
)


def _config(**kwargs) -> BudgetConfig:
    defaults = {
        "enabled": True,
        "monthly_limit_usd": 100.0,
        "alert_at": [0.8, 1.0],
        "pause_on_exceed": False,
        "webhook_url": "https://hooks.slack.com/test",
    }
    defaults.update(kwargs)
    return BudgetConfig(**defaults)


class TestCheckBudget:
    def test_under_budget(self):
        status = check_budget(
            current_spend=30.0,
            new_cost=5.0,
            config=_config(),
        )
        assert status.monthly_spend == 35.0
        assert status.utilization == 0.35
        assert status.exceeded is False
        assert status.alerts_triggered == []

    def test_crosses_80_percent(self):
        status = check_budget(
            current_spend=75.0,
            new_cost=10.0,
            config=_config(),
        )
        assert status.utilization == 0.85
        assert 0.8 in status.alerts_triggered
        assert 1.0 not in status.alerts_triggered

    def test_crosses_100_percent(self):
        status = check_budget(
            current_spend=95.0,
            new_cost=10.0,
            config=_config(),
        )
        assert status.utilization == 1.05
        assert status.exceeded is True
        assert 1.0 in status.alerts_triggered

    def test_crosses_both_thresholds(self):
        status = check_budget(
            current_spend=70.0,
            new_cost=35.0,
            config=_config(),
        )
        assert status.utilization == 1.05
        assert 0.8 in status.alerts_triggered
        assert 1.0 in status.alerts_triggered

    def test_already_past_threshold_no_alert(self):
        status = check_budget(
            current_spend=90.0,
            new_cost=5.0,
            config=_config(),
        )
        assert 0.8 not in status.alerts_triggered
        assert status.exceeded is False

    def test_disabled_budget(self):
        status = check_budget(
            current_spend=500.0,
            new_cost=100.0,
            config=_config(enabled=False),
        )
        assert status.exceeded is False
        assert status.alerts_triggered == []

    def test_zero_limit(self):
        status = check_budget(
            current_spend=10.0,
            new_cost=5.0,
            config=_config(monthly_limit_usd=0),
        )
        assert status.exceeded is False


class TestShouldPauseReview:
    def test_pauses_when_exceeded_and_configured(self):
        status = BudgetStatus(
            monthly_spend=110.0,
            monthly_limit=100.0,
            utilization=1.1,
            exceeded=True,
            alerts_triggered=[1.0],
        )
        assert should_pause_review(status, _config(pause_on_exceed=True)) is True

    def test_no_pause_when_not_exceeded(self):
        status = BudgetStatus(
            monthly_spend=80.0,
            monthly_limit=100.0,
            utilization=0.8,
            exceeded=False,
            alerts_triggered=[],
        )
        assert should_pause_review(status, _config(pause_on_exceed=True)) is False

    def test_no_pause_when_not_configured(self):
        status = BudgetStatus(
            monthly_spend=110.0,
            monthly_limit=100.0,
            utilization=1.1,
            exceeded=True,
            alerts_triggered=[1.0],
        )
        assert should_pause_review(status, _config(pause_on_exceed=False)) is False

    def test_no_pause_when_disabled(self):
        status = BudgetStatus(
            monthly_spend=110.0,
            monthly_limit=100.0,
            utilization=1.1,
            exceeded=True,
            alerts_triggered=[1.0],
        )
        assert should_pause_review(status, _config(enabled=False)) is False


class TestGetMonthlySpend:
    def test_sums_costs(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"cost_usd": 1.5},
            {"cost_usd": 2.3},
            {"cost_usd": 0.8},
        ]
        (
            mock_client.table.return_value
            .select.return_value
            .gte.return_value
            .execute.return_value
        ) = mock_result

        spend = get_monthly_spend(mock_client)
        assert abs(spend - 4.6) < 0.001

    def test_handles_null_costs(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"cost_usd": 1.0},
            {"cost_usd": None},
            {"cost_usd": 2.0},
        ]
        (
            mock_client.table.return_value
            .select.return_value
            .gte.return_value
            .execute.return_value
        ) = mock_result

        spend = get_monthly_spend(mock_client)
        assert abs(spend - 3.0) < 0.001

    def test_returns_zero_on_empty(self):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = []
        (
            mock_client.table.return_value
            .select.return_value
            .gte.return_value
            .execute.return_value
        ) = mock_result

        assert get_monthly_spend(mock_client) == 0.0

    def test_returns_zero_on_exception(self):
        mock_client = MagicMock()
        (
            mock_client.table.return_value
            .select.return_value
            .gte.return_value
            .execute.side_effect
        ) = Exception("DB error")

        assert get_monthly_spend(mock_client) == 0.0


class TestSendBudgetAlert:
    @patch("pr_review_agent.metrics.budget_monitor.requests.post")
    def test_sends_alert_successfully(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        status = BudgetStatus(
            monthly_spend=85.0,
            monthly_limit=100.0,
            utilization=0.85,
            exceeded=False,
            alerts_triggered=[0.8],
        )

        result = send_budget_alert(status, _config(), 0.8)
        assert result is True
        mock_post.assert_called_once()

        body = mock_post.call_args.kwargs["json"]
        assert "80%" in body["text"]
        assert body["attachments"][0]["color"] == "#ffc107"

    @patch("pr_review_agent.metrics.budget_monitor.requests.post")
    def test_red_color_at_100_percent(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        status = BudgetStatus(
            monthly_spend=105.0,
            monthly_limit=100.0,
            utilization=1.05,
            exceeded=True,
            alerts_triggered=[1.0],
        )

        send_budget_alert(status, _config(), 1.0)
        body = mock_post.call_args.kwargs["json"]
        assert body["attachments"][0]["color"] == "#dc3545"

    @patch("pr_review_agent.metrics.budget_monitor.requests.post")
    def test_returns_false_on_http_error(self, mock_post):
        mock_post.return_value = MagicMock(ok=False)
        status = BudgetStatus(
            monthly_spend=85.0,
            monthly_limit=100.0,
            utilization=0.85,
            exceeded=False,
            alerts_triggered=[0.8],
        )

        assert send_budget_alert(status, _config(), 0.8) is False

    def test_returns_false_when_no_url(self):
        status = BudgetStatus(
            monthly_spend=85.0,
            monthly_limit=100.0,
            utilization=0.85,
            exceeded=False,
            alerts_triggered=[0.8],
        )
        assert send_budget_alert(status, _config(webhook_url=""), 0.8) is False

    @patch("pr_review_agent.metrics.budget_monitor.requests.post")
    def test_returns_false_on_network_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.ConnectionError("timeout")
        status = BudgetStatus(
            monthly_spend=85.0,
            monthly_limit=100.0,
            utilization=0.85,
            exceeded=False,
            alerts_triggered=[0.8],
        )

        assert send_budget_alert(status, _config(), 0.8) is False
