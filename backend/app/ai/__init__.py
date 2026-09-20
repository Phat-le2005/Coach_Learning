"""EduMS AI Layer.

Provides external model integration abstractions, routing tiers, gateway resilience,
and observability telemetry with cost estimation.
EduMS does NOT run local models.
Learning core services (Practice, Mastery, Diagnostics, Study Plan) remain 100% functional
even if the AI layer is unavailable. AI has no direct DB write access.
"""

from app.ai.exceptions import (
    AIConfigurationError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AITimeoutError,
)
from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.models import AIRequestLog
from app.ai.pricing import ModelPricing, calculate_estimated_cost, get_model_pricing
from app.ai.prompt_exceptions import PromptNotFoundError, PromptVariableMissingError
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.provider import AIProvider
from app.ai.schemas import (
    AIRequestLogPagination,
    AIRequestLogRead,
    AIUsageSummaryRead,
    DailyUsageMetric,
    TaskTokenMetric,
    TaskUsageMetric,
)
from app.ai.types import (
    AIMessage,
    AIResponse,
    AIRole,
    AIRoutingTier,
    AIStreamChunk,
    AIStructuredResponse,
    AITaskType,
    EmbeddingResponse,
)
from app.ai.usage_service import AIUsageService

__all__ = [
    "AIConfigurationError",
    "AIGateway",
    "AIMessage",
    "AIProvider",
    "AIRateLimitError",
    "AIRequestLog",
    "AIRequestLogPagination",
    "AIRequestLogRead",
    "AIResponse",
    "AIRole",
    "AIRoutingTier",
    "AIServiceUnavailableError",
    "AIStreamChunk",
    "AIStructuredResponse",
    "AITaskType",
    "AITimeoutError",
    "AIUsageService",
    "AIUsageSummaryRead",
    "DailyUsageMetric",
    "EmbeddingResponse",
    "MockAIProvider",
    "ModelPricing",
    "PromptNotFoundError",
    "PromptRegistry",
    "PromptVariableMissingError",
    "TaskTokenMetric",
    "TaskUsageMetric",
    "calculate_estimated_cost",
    "default_prompt_registry",
    "get_model_pricing",
]
