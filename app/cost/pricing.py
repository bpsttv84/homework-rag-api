"""OpenRouter-style model pricing ($ per 1M tokens). Extend as needed."""
from __future__ import annotations

# Single source of truth for cost estimates (homework §6).
PRICES_PER_MILLION: dict[str, dict[str, float]] = {
    "openai/gpt-4o": {"input": 2.5, "output": 10.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "anthropic/claude-3.5-sonnet": {"input": 3.0, "output": 15.0},
    "anthropic/claude-3.5-haiku": {"input": 0.8, "output": 4.0},
    "meta-llama/llama-3.1-8b-instruct": {"input": 0.05, "output": 0.08},
    "meta-llama/llama-3.2-3b-instruct:free": {"input": 0.0, "output": 0.0},
    "google/gemini-2.0-flash-001": {"input": 0.1, "output": 0.4},
    "mistralai/mistral-7b-instruct:free": {"input": 0.0, "output": 0.0},
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICES_PER_MILLION.get(model, {"input": 0.5, "output": 1.5})
    return (input_tokens / 1_000_000.0) * float(p["input"]) + (output_tokens / 1_000_000.0) * float(p["output"])
