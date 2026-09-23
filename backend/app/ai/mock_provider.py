import asyncio
import hashlib
from collections.abc import AsyncIterator
from typing import Any, TypeVar
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from enum import Enum
from uuid import UUID, uuid4

from app.ai.exceptions import AIRateLimitError, AIServiceUnavailableError, AITimeoutError
from app.ai.provider import AIProvider
from app.ai.types import AIMessage, AIResponse, AIRoutingTier

T = TypeVar("T", bound=BaseModel)


def _generate_mock_schema_instance(schema: type[T]) -> T:
    """Generate a minimal valid Pydantic instance for testing if no canned object is specified."""
    values: dict[str, Any] = {}
    for field_name, field_info in schema.model_fields.items():
        if field_info.default is not None and field_info.default not in (..., PydanticUndefined):
            values[field_name] = field_info.default
        elif field_info.default_factory is not None:
            values[field_name] = field_info.default_factory()
        else:
            annotation = field_info.annotation
            annotation_str = str(annotation).lower()
            if isinstance(annotation, type) and issubclass(annotation, Enum):
                values[field_name] = next(iter(annotation)).value
            elif "uuid" in annotation_str:
                values[field_name] = uuid4()
            elif "str" in annotation_str:
                values[field_name] = f"mock_{field_name}"
            elif "int" in annotation_str:
                values[field_name] = 1
            elif "float" in annotation_str:
                values[field_name] = 0.85
            elif "bool" in annotation_str:
                values[field_name] = True
            elif "list" in annotation_str:
                values[field_name] = []
            elif "dict" in annotation_str:
                values[field_name] = {}
            else:
                values[field_name] = None
    return schema.model_validate(values)


class MockAIProvider(AIProvider):
    """Deterministic Mock AI Provider for testing and offline development."""

    def __init__(
        self,
        *,
        default_text: str = "Mock AI Response",
        simulated_latency_s: float = 0.0,
        rate_limit_failures: int = 0,
        service_unavailable_failures: int = 0,
        timeout_failures: int = 0,
        embedding_dimension: int = 768,
        canned_structured: Any = None,
    ) -> None:
        self.default_text = default_text
        self.simulated_latency_s = simulated_latency_s
        self.rate_limit_failures = rate_limit_failures
        self.service_unavailable_failures = service_unavailable_failures
        self.timeout_failures = timeout_failures
        self.embedding_dimension = embedding_dimension
        self.canned_structured = canned_structured

        self.call_count: int = 0
        self.last_model: str | None = None
        self.last_messages: list[AIMessage] | None = None
        self.last_temperature: float | None = None

    async def _handle_simulation(self) -> None:
        self.call_count += 1
        if self.rate_limit_failures > 0:
            self.rate_limit_failures -= 1
            raise AIRateLimitError("Simulated rate limit exceeded.")

        if self.service_unavailable_failures > 0:
            self.service_unavailable_failures -= 1
            raise AIServiceUnavailableError("Simulated 503 service unavailable.")

        if self.timeout_failures > 0:
            self.timeout_failures -= 1
            raise AITimeoutError("Simulated provider timeout.")

        if self.simulated_latency_s > 0:
            await asyncio.sleep(self.simulated_latency_s)

    async def generate(
        self,
        messages: list[AIMessage],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 30.0,
    ) -> AIResponse:
        self.last_model = model
        self.last_messages = messages
        self.last_temperature = temperature
        await self._handle_simulation()

        content = self.default_text
        return AIResponse(
            content=content,
            model=model,
            tier=AIRoutingTier.FAST,
            tokens_used=42,
            latency_ms=self.simulated_latency_s * 1000,
        )

    async def generate_structured(
        self,
        messages: list[AIMessage],
        schema: type[T],
        model: str,
        *,
        temperature: float = 0.2,
        timeout: float = 30.0,
    ) -> T:
        self.last_model = model
        self.last_messages = messages
        self.last_temperature = temperature
        await self._handle_simulation()

        if self.canned_structured is not None:
            if isinstance(self.canned_structured, schema):
                return self.canned_structured
            if isinstance(self.canned_structured, dict):
                return schema.model_validate(self.canned_structured)

        return _generate_mock_schema_instance(schema)

    async def stream(
        self,
        messages: list[AIMessage],
        model: str,
        *,
        temperature: float = 0.7,
        timeout: float = 30.0,
    ) -> AsyncIterator[str]:
        self.last_model = model
        self.last_messages = messages
        self.last_temperature = temperature
        await self._handle_simulation()

        words = self.default_text.split(" ")
        for word in words:
            yield word + " "
            if self.simulated_latency_s > 0:
                await asyncio.sleep(min(self.simulated_latency_s, 0.05))

    async def embed(
        self,
        texts: list[str],
        model: str,
        *,
        timeout: float = 30.0,
    ) -> list[list[float]]:
        import math
        import re

        self.last_model = model
        await self._handle_simulation()

        results: list[list[float]] = []
        for text in texts:
            words = re.findall(r"\w+", text.lower())
            if not words:
                results.append([0.0] * self.embedding_dimension)
                continue

            vector = [0.0] * self.embedding_dimension
            for word in words:
                digest = hashlib.sha256(word.encode("utf-8")).digest()
                for k in range(4):
                    idx = int.from_bytes(digest[k * 4 : (k + 1) * 4], "little") % self.embedding_dimension
                    sign = 1.0 if digest[16 + k] % 2 == 0 else -1.0
                    vector[idx] += sign

            norm = math.sqrt(sum(x * x for x in vector))
            if norm == 0.0:
                results.append([0.0] * self.embedding_dimension)
            else:
                results.append([round(x / norm, 4) for x in vector])

        return results
