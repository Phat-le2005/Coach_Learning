from app.ai.types import (
    AIRoutingTier,
    AITaskType,
    DEFAULT_TASK_TIER_MAPPING,
)
from app.core.config import Settings


class ModelRoutingPolicy:
    """Manages AI model routing tiers (FAST, STANDARD, REASONING) with environment-based model identifiers.
    
    Responsibilities:
    - Maps AITaskType to AIRoutingTier (FAST, STANDARD, REASONING).
    - Resolves tier to concrete model identifiers configured via application settings.
    - Ensures changes in environment variables dynamically propagate to model routing.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve_tier(
        self,
        task_type: AITaskType,
        override: AIRoutingTier | None = None,
    ) -> AIRoutingTier:
        """Map task type to the appropriate latency/reasoning tier."""
        if override is not None:
            return override
        return DEFAULT_TASK_TIER_MAPPING.get(task_type, AIRoutingTier.STANDARD)

    def resolve_model(self, tier: AIRoutingTier) -> str:
        """Retrieve model identifier configured for the specified tier from environment settings."""
        if tier == AIRoutingTier.FAST:
            return self.settings.ai_model_fast
        elif tier == AIRoutingTier.STANDARD:
            return self.settings.ai_model_standard
        elif tier == AIRoutingTier.REASONING:
            return self.settings.ai_model_reasoning
        return self.settings.ai_model_standard

    def resolve_model_for_task(
        self,
        task_type: AITaskType,
        override: AIRoutingTier | None = None,
    ) -> str:
        """Resolve concrete model name directly for a given task type."""
        tier = self.resolve_tier(task_type, override)
        return self.resolve_model(tier)

    def resolve_embedding_model(self) -> str:
        """Retrieve configured model identifier for embeddings."""
        return self.settings.ai_embedding_model
