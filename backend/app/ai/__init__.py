"""EduMS AI Layer.

Provides external model integration abstractions, routing tiers, gateway resilience,
and observability telemetry with cost estimation.
EduMS does NOT run local models.
Learning core services (Practice, Mastery, Diagnostics, Study Plan) remain 100% functional
even if the AI layer is unavailable. AI has no direct DB write access.
"""

from app.ai.context_trimmer import ContextTrimmer
from app.ai.error_mapper import AIErrorMapper
from app.ai.exceptions import (
    AIActionNotAllowedError,
    AIConfigurationError,
    AIFakeCurriculumCodeError,
    AIForbiddenMutationError,
    AIInvalidJSONError,
    AIOutputValidationError,
    AIPromptInjectionError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AITimeoutError,
    AIUnknownActionError,
)
from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.models import AIRequestLog
from app.ai.pricing import ModelPricing, calculate_estimated_cost, get_model_pricing
from app.ai.prompt_exceptions import PromptNotFoundError, PromptVariableMissingError
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.provider import AIProvider
from app.ai.rate_limiter import AIRateLimiter, ai_rate_limiter, require_ai_rate_limit
from app.ai.routing_policy import ModelRoutingPolicy
from app.ai.schemas import (
    AIRequestLogPagination,
    AIRequestLogRead,
    AIUsageSummaryRead,
    DailyUsageMetric,
    StudentDailyUsageMetric,
    TaskTokenMetric,
    TaskUsageMetric,
)
from app.ai.tool_policy import AIToolPolicy
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
from app.ai.validator import AIOutputValidator

__all__ = [
    "AIActionNotAllowedError",
    "AIConfigurationError",
    "AIErrorMapper",
    "AIFakeCurriculumCodeError",
    "AIForbiddenMutationError",
    "AIGateway",
    "AIInvalidJSONError",
    "AIMessage",
    "AIOutputValidationError",
    "AIOutputValidator",
    "AIPromptInjectionError",
    "AIProvider",
    "AIRateLimiter",
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
    "AIToolPolicy",
    "AIUnknownActionError",
    "AIUsageService",
    "AIUsageSummaryRead",
    "ContextTrimmer",
    "DailyUsageMetric",
    "EmbeddingResponse",
    "MockAIProvider",
    "ModelPricing",
    "ModelRoutingPolicy",
    "PromptNotFoundError",
    "PromptRegistry",
    "PromptVariableMissingError",
    "StudentDailyUsageMetric",
    "TaskTokenMetric",
    "TaskUsageMetric",
    "ai_rate_limiter",
    "calculate_estimated_cost",
    "default_prompt_registry",
    "get_model_pricing",
    "require_ai_rate_limit",
]
