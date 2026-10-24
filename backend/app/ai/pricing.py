from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Pricing rates per 1,000,000 tokens in USD."""
    input_cost_per_million: float
    output_cost_per_million: float


# Dedicated pricing configuration decoupled from business logic
DEFAULT_MODEL_PRICING: dict[str, ModelPricing] = {
    "gemini-3.6-flash": ModelPricing(input_cost_per_million=1.50, output_cost_per_million=7.50),
    "gemini-2.5-flash": ModelPricing(input_cost_per_million=0.075, output_cost_per_million=0.30),
    "gemini-2.5-standard": ModelPricing(input_cost_per_million=0.50, output_cost_per_million=2.00),
    "gemini-2.5-pro": ModelPricing(input_cost_per_million=1.25, output_cost_per_million=5.00),
    "text-embedding-004": ModelPricing(input_cost_per_million=0.025, output_cost_per_million=0.0),
    "mock": ModelPricing(input_cost_per_million=0.0, output_cost_per_million=0.0),
}


def get_model_pricing(model: str) -> ModelPricing:
    """Lookup pricing rate for a model, defaulting to zero-cost if unspecified."""
    normalized_name = model.lower().strip()
    return DEFAULT_MODEL_PRICING.get(
        normalized_name,
        ModelPricing(input_cost_per_million=0.0, output_cost_per_million=0.0),
    )


def calculate_estimated_cost(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float:
    """Calculate estimated cost in USD based on input/output token counts."""
    pricing = get_model_pricing(model)
    in_tok = max(0, input_tokens or 0)
    out_tok = max(0, output_tokens or 0)

    input_cost = (in_tok / 1_000_000.0) * pricing.input_cost_per_million
    output_cost = (out_tok / 1_000_000.0) * pricing.output_cost_per_million
    return round(input_cost + output_cost, 6)
