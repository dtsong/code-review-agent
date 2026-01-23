"""Token usage tracking and cost calculation."""

from dataclasses import dataclass

# Pricing per 1K tokens (USD)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005},
    "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
}


@dataclass
class TokenUsage:
    """Token usage for a single API call."""

    input_tokens: int
    output_tokens: int
    model: str
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a given model and token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-sonnet-4-20250514"])
    input_cost = (input_tokens * pricing["input"]) / 1000
    output_cost = (output_tokens * pricing["output"]) / 1000
    return input_cost + output_cost


def track_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> TokenUsage:
    """Create a TokenUsage record from API response data."""
    cost = calculate_cost(model, input_tokens, output_tokens)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        cost_usd=cost,
    )
