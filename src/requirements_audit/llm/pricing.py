"""Token pricing — the basis for the per-run cost *estimate* in traces.

Prices are pinned here alongside the model pins in `config.py` (USD per million
tokens, as of 2026-07) and reviewed when a model version is bumped. The output
is always labeled an estimate: it prices the *configured* primary model, so a
run that silently used the fallback provider is priced as if it were primary —
exact per-provider accounting is what the live provider-comparison run measures.
"""

from __future__ import annotations

# model name -> (input USD/Mtok, output USD/Mtok)
MODEL_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
}


def estimate_usd(model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated cost for a token count, or None when the model has no pin —
    an unknown model must show as 'unpriced', never as $0.00."""
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model_name)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
