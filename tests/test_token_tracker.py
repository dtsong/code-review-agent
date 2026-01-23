"""Tests for token usage tracking."""

from pr_review_agent.metrics.token_tracker import (
    TokenUsage,
    calculate_cost,
    track_usage,
)


def test_calculate_cost_sonnet():
    """Calculate cost for Sonnet model."""
    cost = calculate_cost("claude-sonnet-4-20250514", 1000, 500)

    # 1000 * 0.003/1000 + 500 * 0.015/1000 = 0.003 + 0.0075 = 0.0105
    assert abs(cost - 0.0105) < 1e-6


def test_calculate_cost_haiku():
    """Calculate cost for Haiku model."""
    cost = calculate_cost("claude-haiku-4-5-20251001", 1000, 500)

    # 1000 * 0.001/1000 + 500 * 0.005/1000 = 0.001 + 0.0025 = 0.0035
    assert abs(cost - 0.0035) < 1e-6


def test_calculate_cost_opus():
    """Calculate cost for Opus model."""
    cost = calculate_cost("claude-opus-4-20250514", 1000, 500)

    # 1000 * 0.015/1000 + 500 * 0.075/1000 = 0.015 + 0.0375 = 0.0525
    assert abs(cost - 0.0525) < 1e-6


def test_calculate_cost_unknown_model_defaults_to_sonnet():
    """Unknown model falls back to Sonnet pricing."""
    cost = calculate_cost("unknown-model", 1000, 500)

    expected = calculate_cost("claude-sonnet-4-20250514", 1000, 500)
    assert cost == expected


def test_track_usage():
    """Track usage creates a proper TokenUsage record."""
    usage = track_usage("claude-sonnet-4-20250514", 2000, 1000)

    assert usage.input_tokens == 2000
    assert usage.output_tokens == 1000
    assert usage.model == "claude-sonnet-4-20250514"
    assert usage.cost_usd > 0


def test_token_usage_total_tokens():
    """TokenUsage.total_tokens sums input and output."""
    usage = TokenUsage(
        input_tokens=1500,
        output_tokens=500,
        model="claude-sonnet-4-20250514",
        cost_usd=0.01,
    )

    assert usage.total_tokens == 2000
