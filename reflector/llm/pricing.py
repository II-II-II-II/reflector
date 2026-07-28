"""
$ per 1M tokens, input/output. Manually maintained — check provider pricing
pages before trusting this for anything beyond a rough estimate. Local
(Ollama) is free and intentionally absent; unlisted model_ids estimate as
unknown rather than silently showing $0.
"""

USD_PER_MILLION_TOKENS = {
    "deepseek.v3.2": (0.62, 1.85),
    "us.anthropic.claude-sonnet-5": (2.00, 10.00),
    "anthropic.claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
}


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float | None:
    rates = USD_PER_MILLION_TOKENS.get(model_id)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
