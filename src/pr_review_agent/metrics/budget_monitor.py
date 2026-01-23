"""Budget monitoring with alerts for cost limits."""

from dataclasses import dataclass
from datetime import UTC, datetime

import requests

from pr_review_agent.config import BudgetConfig


@dataclass
class BudgetStatus:
    """Current budget status."""

    monthly_spend: float
    monthly_limit: float
    utilization: float  # 0.0 to 1.0+
    exceeded: bool
    alerts_triggered: list[float]  # thresholds that were crossed


def get_monthly_spend(supabase_client) -> float:
    """Query current month's total spend from Supabase."""
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        result = (
            supabase_client.table("review_events")
            .select("cost_usd")
            .gte("created_at", month_start.isoformat())
            .execute()
        )
        if result.data:
            return sum(r["cost_usd"] or 0 for r in result.data)
        return 0.0
    except Exception:
        return 0.0


def check_budget(
    current_spend: float,
    new_cost: float,
    config: BudgetConfig,
) -> BudgetStatus:
    """Check if budget thresholds are crossed after adding new_cost."""
    if not config.enabled or config.monthly_limit_usd <= 0:
        return BudgetStatus(
            monthly_spend=current_spend + new_cost,
            monthly_limit=config.monthly_limit_usd,
            utilization=0.0,
            exceeded=False,
            alerts_triggered=[],
        )

    total_spend = current_spend + new_cost
    utilization = total_spend / config.monthly_limit_usd

    # Determine which alert thresholds were newly crossed
    prev_utilization = current_spend / config.monthly_limit_usd
    alerts_triggered = [
        threshold
        for threshold in sorted(config.alert_at)
        if prev_utilization < threshold <= utilization
    ]

    return BudgetStatus(
        monthly_spend=total_spend,
        monthly_limit=config.monthly_limit_usd,
        utilization=utilization,
        exceeded=utilization >= 1.0,
        alerts_triggered=alerts_triggered,
    )


def should_pause_review(status: BudgetStatus, config: BudgetConfig) -> bool:
    """Determine if reviews should be paused due to budget."""
    if not config.enabled:
        return False
    return config.pause_on_exceed and status.exceeded


def send_budget_alert(
    status: BudgetStatus,
    config: BudgetConfig,
    threshold: float,
) -> bool:
    """Send a budget alert webhook. Returns True on success."""
    if not config.webhook_url:
        return False

    percentage = int(threshold * 100)
    body = {
        "text": (
            f"Budget Alert: {percentage}% of monthly limit reached.\n"
            f"Spend: ${status.monthly_spend:.2f} / "
            f"${status.monthly_limit:.2f} "
            f"({status.utilization:.0%} utilized)"
        ),
        "attachments": [
            {
                "color": "#dc3545" if threshold >= 1.0 else "#ffc107",
                "fields": [
                    {
                        "title": "Monthly Spend",
                        "value": f"${status.monthly_spend:.2f}",
                        "short": True,
                    },
                    {
                        "title": "Monthly Limit",
                        "value": f"${status.monthly_limit:.2f}",
                        "short": True,
                    },
                    {
                        "title": "Utilization",
                        "value": f"{status.utilization:.0%}",
                        "short": True,
                    },
                    {
                        "title": "Threshold",
                        "value": f"{percentage}%",
                        "short": True,
                    },
                ],
            }
        ],
    }

    try:
        response = requests.post(config.webhook_url, json=body, timeout=10)
        return response.ok
    except requests.RequestException:
        return False
