import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

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
from app.core.exceptions import ApplicationError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AIErrorMapper:
    """Standardized error mapping and resilience wrapper for the AI Layer.
    
    Responsibilities:
    - Normalizes diverse external provider errors (Gemini, OpenAI, HTTP clients, timeouts)
      into domain-specific ApplicationError subclasses.
    - Preserves learning core independence by preventing AI outages from breaking core flows.
    """

    @staticmethod
    def map_exception(exc: Exception) -> ApplicationError:
        """Map any exception to a typed ApplicationError subclass.
        
        Args:
            exc: Caught exception.
            
        Returns:
            Mapped ApplicationError.
        """
        # 1. If already a domain ApplicationError, preserve it
        if isinstance(
            exc,
            (
                AITimeoutError,
                AIRateLimitError,
                AIServiceUnavailableError,
                AIConfigurationError,
                AIOutputValidationError,
                AIInvalidJSONError,
                AIFakeCurriculumCodeError,
                AIUnknownActionError,
                AIActionNotAllowedError,
                AIForbiddenMutationError,
                AIPromptInjectionError,
            ),
        ):
            return exc

        exc_name = type(exc).__name__.lower()
        exc_msg = str(exc).lower()

        # 2. Timeout mapping
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in exc_name or "timed out" in exc_msg:
            return AITimeoutError(f"AI gateway operation timed out: {exc}")

        # 3. Rate limit mapping
        if "ratelimit" in exc_name or "429" in exc_msg or "quota exceeded" in exc_msg or "too many requests" in exc_msg:
            return AIRateLimitError(f"AI service rate limit exceeded: {exc}")

        # 4. Service unavailable mapping (503, 502, connection errors, DNS failure)
        if (
            isinstance(exc, ConnectionError)
            or "connection" in exc_name
            or "serviceunavailable" in exc_name
            or "503" in exc_msg
            or "502" in exc_msg
            or "network" in exc_msg
        ):
            return AIServiceUnavailableError(f"AI service is unavailable: {type(exc).__name__}: {exc}")

        # 5. Default fallback to AIServiceUnavailableError
        logger.error("ai_error_mapper: unhandled exception mapped to 503: %s", exc, exc_info=True)
        return AIServiceUnavailableError(f"AI service encountered an unhandled error: {type(exc).__name__}: {exc}")

    @classmethod
    async def safe_execute(
        cls,
        coro: Coroutine[Any, Any, T],
        *,
        fallback_value: T | None = None,
        operation_name: str = "ai_operation",
    ) -> T | None:
        """Safely execute an AI operation without propagating exceptions to the caller.
        
        Guarantees that the Learning Core (mastery calculation, question fetching,
        practice session progress) is never disrupted by an AI provider failure.
        
        Args:
            coro: Asynchronous coroutine to execute.
            fallback_value: Default value to return on failure.
            operation_name: Identifier for logging.
            
        Returns:
            The coroutine result, or `fallback_value` if an error occurred.
        """
        try:
            return await coro
        except Exception as exc:
            mapped = cls.map_exception(exc)
            logger.warning(
                "ai_error_mapper: safe_execute caught error in %s: [%s] %s. Returning fallback.",
                operation_name,
                type(mapped).__name__,
                mapped.message,
            )
            return fallback_value
