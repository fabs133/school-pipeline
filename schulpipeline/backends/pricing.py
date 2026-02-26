"""Backend pricing data and cost estimation utilities."""

from __future__ import annotations

from typing import Any

# Approximate token counts per stage (based on observed usage).
# {stage: (tokens_in, tokens_out)}
STAGE_TOKEN_ESTIMATES: dict[str, tuple[int, int]] = {
    "intake": (500, 400),
    "plan": (800, 600),
    "research": (1200, 2000),
    "synthesize": (2500, 3000),
    "artifact": (0, 0),  # no LLM call
}

# Price per 1M tokens: {backend_name: (input_price, output_price)}
BACKEND_PRICING: dict[str, tuple[float, float]] = {
    "groq": (0.0, 0.0),
    "gemini": (0.0, 0.0),
    "mistral": (0.0, 0.0),
    "ollama": (0.0, 0.0),
    "openai": (0.15, 0.60),  # gpt-4o-mini
}


def estimate_stage_cost(stage_name: str, backend_name: str) -> float:
    """Estimate cost in USD for a single stage on a given backend."""
    tokens_in, tokens_out = STAGE_TOKEN_ESTIMATES.get(stage_name, (1000, 1000))
    price_in, price_out = BACKEND_PRICING.get(backend_name, (0.0, 0.0))
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def estimate_pipeline_cost(
    stages: list[str],
    cascade: dict[str, list[str]],
) -> tuple[float, dict[str, dict[str, Any]]]:
    """Estimate total cost for a pipeline run.

    Uses the first backend in each stage's cascade (the most likely to be used).

    Returns:
        (total_cost_usd, breakdown) where breakdown maps
        stage -> {"backend", "cost_usd", "tokens_in", "tokens_out"}
    """
    total = 0.0
    breakdown: dict[str, dict[str, Any]] = {}

    for stage_name in stages:
        backends = cascade.get(stage_name, [])
        backend_name = backends[0] if backends else "unknown"

        tokens_in, tokens_out = STAGE_TOKEN_ESTIMATES.get(stage_name, (1000, 1000))
        cost = estimate_stage_cost(stage_name, backend_name)

        breakdown[stage_name] = {
            "backend": backend_name,
            "cost_usd": cost,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        total += cost

    return total, breakdown
