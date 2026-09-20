import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, TypeVar
from pydantic import BaseModel

from app.ai.exceptions import (
    AIRateLimitError,
    AIServiceUnavailableError,
    AITimeoutError,
)
from app.ai.provider import AIProvider
from app.ai.types import (
    AIMessage,
    AIResponse,
    AIRole,
    AIRoutingTier,
    AIStructuredResponse,
    AITaskType,
    DEFAULT_TASK_TIER_MAPPING,
    EmbeddingResponse,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AIGateway:
    """Central gateway for all EduMS AI invocations.
    
    Responsibilities:
    - Resolves routing tiers (FAST, STANDARD, REASONING) and models based on task type.
    - Decouples domain callers from concrete providers (Gemini, OpenAI, Mock, etc.).
    - Enforces request timeouts.
    - Handles limited retries for transient errors (rate-limit 429, temporary network issues).
    - Records latency metrics for observability.
    - Safely maps provider errors to AIServiceUnavailableError (503).
    - Enforces DB isolation: AI has NO direct database write permissions for learning state.
    """

    def __init__(self, provider: AIProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    def resolve_tier(
        self,
        task_type: AITaskType,
        tier_override: AIRoutingTier | None = None,
    ) -> AIRoutingTier:
        """Map task type to the appropriate latency/reasoning tier."""
        if tier_override is not None:
            return tier_override
        return DEFAULT_TASK_TIER_MAPPING.get(task_type, AIRoutingTier.STANDARD)

    def resolve_model(self, tier: AIRoutingTier) -> str:
        """Retrieve model identifier configured for the specified tier."""
        if tier == AIRoutingTier.FAST:
            return self.settings.ai_model_fast
        elif tier == AIRoutingTier.STANDARD:
            return self.settings.ai_model_standard
        elif tier == AIRoutingTier.REASONING:
            return self.settings.ai_model_reasoning
        return self.settings.ai_model_standard

    def resolve_embedding_model(self) -> str:
        """Retrieve configured model identifier for embeddings."""
        return self.settings.ai_embedding_model

    def _normalize_messages(self, messages: list[AIMessage] | list[dict[str, Any]] | str) -> list[AIMessage]:
        if isinstance(messages, str):
            return [AIMessage(role=AIRole.USER, content=messages)]
        normalized: list[AIMessage] = []
        for msg in messages:
            if isinstance(msg, AIMessage):
                normalized.append(msg)
            elif isinstance(msg, dict):
                normalized.append(AIMessage(role=msg.get("role", AIRole.USER), content=msg.get("content", "")))
        return normalized

    async def _execute_with_resilience(
        self,
        task_type: AITaskType,
        tier: AIRoutingTier,
        model: str,
        operation_name: str,
        func: Any,
        timeout: float | None = None,
    ) -> Any:
        timeout_seconds = timeout or self.settings.ai_timeout_seconds
        max_retries = self.settings.ai_max_retries
        backoff_base_s = 0.1

        start_time = time.perf_counter()
        attempt = 0

        while True:
            try:
                async with asyncio.timeout(timeout_seconds):
                    result = await func()
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                logger.info(
                    "ai_gateway_call_success task_type=%s tier=%s model=%s op=%s latency_ms=%.2f attempts=%d",
                    task_type,
                    tier,
                    model,
                    operation_name,
                    latency_ms,
                    attempt + 1,
                )
                return result, latency_ms

            except (AIRateLimitError, TimeoutError, asyncio.TimeoutError, ConnectionError) as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                if attempt < max_retries:
                    attempt += 1
                    sleep_time = backoff_base_s * (2 ** (attempt - 1))
                    logger.warning(
                        "ai_gateway_retry task_type=%s tier=%s model=%s op=%s attempt=%d/%d error=%s sleep_s=%.2f",
                        task_type,
                        tier,
                        model,
                        operation_name,
                        attempt,
                        max_retries,
                        type(exc).__name__,
                        sleep_time,
                    )
                    await asyncio.sleep(sleep_time)
                    continue

                logger.error(
                    "ai_gateway_retries_exhausted task_type=%s tier=%s model=%s op=%s latency_ms=%.2f error=%s",
                    task_type,
                    tier,
                    model,
                    operation_name,
                    latency_ms,
                    exc,
                )
                if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
                    raise AITimeoutError("AI gateway request timed out after retries.") from exc
                if isinstance(exc, AIRateLimitError):
                    raise AIRateLimitError("AI service rate limit exceeded.") from exc
                raise AIServiceUnavailableError(f"AI service unavailable: {type(exc).__name__}") from exc

            except (AIServiceUnavailableError, AITimeoutError):
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                logger.error(
                    "ai_gateway_service_error task_type=%s tier=%s model=%s op=%s latency_ms=%.2f",
                    task_type,
                    tier,
                    model,
                    operation_name,
                    latency_ms,
                )
                raise

            except Exception as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                logger.error(
                    "ai_gateway_unexpected_error task_type=%s tier=%s model=%s op=%s latency_ms=%.2f error=%s",
                    task_type,
                    tier,
                    model,
                    operation_name,
                    latency_ms,
                    type(exc).__name__,
                    exc_info=True,
                )
                raise AIServiceUnavailableError(
                    f"AI service encountered an unexpected error: {type(exc).__name__}"
                ) from exc

    async def generate(
        self,
        task_type: AITaskType,
        messages: list[AIMessage] | list[dict[str, Any]] | str,
        *,
        tier: AIRoutingTier | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float | None = None,
        prompt_name: str = "default",
        prompt_version: str = "v1",
        user_id: Any = None,
        usage_service: Any = None,
    ) -> AIResponse:
        """Generate a completion for the given AI task type with automatic tier routing."""
        effective_tier = self.resolve_tier(task_type, tier)
        effective_model = self.resolve_model(effective_tier)
        norm_messages = self._normalize_messages(messages)

        async def _call() -> AIResponse:
            return await self.provider.generate(
                messages=norm_messages,
                model=effective_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout or self.settings.ai_timeout_seconds,
            )

        try:
            resp, latency_ms = await self._execute_with_resilience(
                task_type=task_type,
                tier=effective_tier,
                model=effective_model,
                operation_name="generate",
                func=_call,
                timeout=timeout,
            )
            resp.tier = effective_tier
            resp.model = effective_model
            resp.latency_ms = latency_ms

            if usage_service is not None:
                try:
                    usage_service.record_log(
                        task=task_type,
                        provider=self.settings.ai_provider,
                        model=effective_model,
                        latency_ms=latency_ms,
                        prompt_name=prompt_name,
                        prompt_version=prompt_version,
                        input_tokens=getattr(resp, "tokens_used", None),
                        output_tokens=None,
                        success=True,
                        user_id=user_id,
                    )
                except Exception as log_err:
                    logger.warning("Failed to record AIRequestLog: %s", log_err)

            return resp
        except Exception as exc:
            if usage_service is not None:
                try:
                    usage_service.record_log(
                        task=task_type,
                        provider=self.settings.ai_provider,
                        model=effective_model,
                        latency_ms=0.0,
                        prompt_name=prompt_name,
                        prompt_version=prompt_version,
                        success=False,
                        error_type=type(exc).__name__,
                        user_id=user_id,
                    )
                except Exception as log_err:
                    logger.warning("Failed to record AIRequestLog error: %s", log_err)
            raise

    async def generate_structured(
        self,
        task_type: AITaskType,
        schema: type[T],
        messages: list[AIMessage] | list[dict[str, Any]] | str,
        *,
        tier: AIRoutingTier | None = None,
        temperature: float = 0.2,
        timeout: float | None = None,
        prompt_name: str = "default",
        prompt_version: str = "v1",
        user_id: Any = None,
        usage_service: Any = None,
    ) -> AIStructuredResponse[T]:
        """Generate a validated Pydantic model response adhering strictly to schema."""
        effective_tier = self.resolve_tier(task_type, tier)
        effective_model = self.resolve_model(effective_tier)
        norm_messages = self._normalize_messages(messages)

        async def _call() -> T:
            return await self.provider.generate_structured(
                messages=norm_messages,
                schema=schema,
                model=effective_model,
                temperature=temperature,
                timeout=timeout or self.settings.ai_timeout_seconds,
            )

        try:
            parsed_data, latency_ms = await self._execute_with_resilience(
                task_type=task_type,
                tier=effective_tier,
                model=effective_model,
                operation_name="generate_structured",
                func=_call,
                timeout=timeout,
            )

            if usage_service is not None:
                try:
                    usage_service.record_log(
                        task=task_type,
                        provider=self.settings.ai_provider,
                        model=effective_model,
                        latency_ms=latency_ms,
                        prompt_name=prompt_name,
                        prompt_version=prompt_version,
                        input_tokens=None,
                        output_tokens=None,
                        success=True,
                        user_id=user_id,
                    )
                except Exception as log_err:
                    logger.warning("Failed to record AIRequestLog: %s", log_err)

            return AIStructuredResponse[T](
                data=parsed_data,
                raw_content=parsed_data.model_dump_json(),
                model=effective_model,
                tier=effective_tier,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            if usage_service is not None:
                try:
                    usage_service.record_log(
                        task=task_type,
                        provider=self.settings.ai_provider,
                        model=effective_model,
                        latency_ms=0.0,
                        prompt_name=prompt_name,
                        prompt_version=prompt_version,
                        success=False,
                        error_type=type(exc).__name__,
                        user_id=user_id,
                    )
                except Exception as log_err:
                    logger.warning("Failed to record AIRequestLog error: %s", log_err)
            raise

    async def stream(
        self,
        task_type: AITaskType,
        messages: list[AIMessage] | list[dict[str, Any]] | str,
        *,
        tier: AIRoutingTier | None = None,
        temperature: float = 0.7,
        timeout: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream chunks from the model for the given task type."""
        effective_tier = self.resolve_tier(task_type, tier)
        effective_model = self.resolve_model(effective_tier)
        norm_messages = self._normalize_messages(messages)

        logger.info(
            "ai_gateway_stream_start task_type=%s tier=%s model=%s",
            task_type,
            effective_tier,
            effective_model,
        )
        try:
            async for chunk in self.provider.stream(
                messages=norm_messages,
                model=effective_model,
                temperature=temperature,
                timeout=timeout or self.settings.ai_timeout_seconds,
            ):
                yield chunk
        except Exception as exc:
            logger.error("ai_gateway_stream_error task_type=%s error=%s", task_type, exc)
            raise AIServiceUnavailableError(f"Streaming failed: {type(exc).__name__}") from exc

    async def embed(
        self,
        texts: list[str],
        *,
        timeout: float | None = None,
    ) -> EmbeddingResponse:
        """Generate high-dimensional vector embeddings for text chunks."""
        effective_model = self.resolve_embedding_model()

        async def _call() -> list[list[float]]:
            return await self.provider.embed(
                texts=texts,
                model=effective_model,
                timeout=timeout or self.settings.ai_timeout_seconds,
            )

        vectors, latency_ms = await self._execute_with_resilience(
            task_type=AITaskType.RAG,
            tier=AIRoutingTier.FAST,
            model=effective_model,
            operation_name="embed",
            func=_call,
            timeout=timeout,
        )
        dimension = len(vectors[0]) if vectors else 0
        return EmbeddingResponse(
            embeddings=vectors,
            model=effective_model,
            dimension=dimension,
            latency_ms=latency_ms,
        )
