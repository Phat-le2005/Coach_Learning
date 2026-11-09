"""Gemini REST provider. Keys stay server-side; provider failures never synthesize grades."""

from collections.abc import AsyncIterator
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.ai.exceptions import (
    AIConfigurationError,
    AIOutputValidationError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AITimeoutError,
)
from app.ai.provider import AIProvider
from app.ai.types import AIMessage, AIResponse, AIRoutingTier
from app.ai.gemini_failover import (
    AttemptFailure,
    Execution,
    GeminiFailoverManager,
    Payload,
    PoolUnavailable,
    classify_failure,
    generation_parameters,
    get_gemini_manager,
)
from app.core.config import Settings
from dataclasses import replace

T = TypeVar("T", bound=BaseModel)
_MODEL_ID = re.compile(r"^[a-zA-Z0-9._-]+$")
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

import copy
import logging

logger = logging.getLogger(__name__)


def _sanitize_schema_for_gemini(raw_schema: dict) -> dict:
    """Sanitize OpenAPI/Pydantic schema for Gemini REST API requirements."""
    defs = raw_schema.get("$defs", {}) or raw_schema.get("definitions", {})

    def resolve(node):
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"].split("/")[-1]
            return resolve(copy.deepcopy(defs.get(ref, {})))
        res = {}
        for k, v in node.items():
            if k == "properties" and isinstance(v, dict):
                # Names such as "title" are data properties here, not schema
                # metadata. Keep them consistent with the required-name list.
                res[k] = {name: resolve(child) for name, child in v.items()}
                continue
            if k in (
                "$defs",
                "definitions",
                "title",
                "description",
                "default",
                "additionalProperties",
                "minLength",
                "maxLength",
                "pattern",
                "minItems",
                "maxItems",
                "minimum",
                "maximum",
            ):
                continue
            if k == "anyOf":
                non_null = [
                    item
                    for item in v
                    if isinstance(item, dict) and item.get("type") != "null"
                ]
                has_null = len(non_null) < len(v)
                if len(non_null) == 1:
                    child = resolve(non_null[0])
                    res.update(child)
                    if has_null:
                        res["nullable"] = True
                    continue
            if isinstance(v, dict):
                res[k] = resolve(v)
            elif isinstance(v, list):
                res[k] = [resolve(i) for i in v]
            else:
                res[k] = v
        return res

    cleaned = resolve(copy.deepcopy(raw_schema))
    try:
        step_items = cleaned["properties"]["steps"]["items"]
        props = step_items["properties"]
        if "verdict" in props and "enum" not in props["verdict"]:
            props["verdict"]["enum"] = ["VALID", "INVALID", "NEEDS_REVIEW"]
        req = step_items.setdefault("required", [])
        if "score" in props and "score" not in req:
            req.append("score")
    except Exception:
        pass
    return cleaned


class GeminiProvider(AIProvider):
    """Use generateContent with JSON mode and strict local schema validation."""

    manages_failover = True

    def __init__(
        self,
        api_key: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        settings: Settings | None = None,
        manager: GeminiFailoverManager | None = None,
    ) -> None:
        try:
            self.manager = manager or (
                get_gemini_manager(settings)
                if settings is not None
                else GeminiFailoverManager.single_key(api_key)
            )
        except PoolUnavailable:
            raise AIConfigurationError(
                "Gemini key pool configuration is invalid."
            ) from None
        if not self.manager.credentials:
            raise AIConfigurationError("Gemini API key is not configured.")
        self._transport = transport

    @property
    def _api_key(self):
        """Legacy read access; scheduling always uses the shared pool."""
        return self.manager.credentials[0].secret.get_secret_value()

    async def _request(
        self,
        messages: list[AIMessage],
        model: str,
        *,
        temperature: float,
        timeout: float,
        json_mode: bool = False,
        response_schema: dict | None = None,
        task: str = "DEFAULT",
        parse=None,
        max_tokens: int | None = None,
    ) -> Execution:
        if not _MODEL_ID.fullmatch(model):
            raise AIConfigurationError("Invalid Gemini model identifier.")
        system_text = "\n".join(m.content for m in messages if str(m.role) == "system")
        contents = [
            {
                "role": "model" if str(m.role) == "assistant" else "user",
                "parts": [{"text": m.content}],
            }
            for m in messages
            if str(m.role) != "system"
        ]
        if not contents:
            raise AIConfigurationError("Gemini request has no user content.")
        base: dict[str, object] = {
            "contents": contents,
        }
        if system_text:
            base["systemInstruction"] = {"parts": [{"text": system_text}]}

        async def send(choice, budget):
            config = generation_parameters(choice.model, temperature=temperature)
            if json_mode:
                config["responseMimeType"] = "application/json"
            if response_schema is not None:
                config["responseJsonSchema"] = _sanitize_schema_for_gemini(
                    response_schema
                )
            if max_tokens is not None:
                config["maxOutputTokens"] = max_tokens
            body = {**base, "generationConfig": config}
            try:
                async with httpx.AsyncClient(
                    timeout=budget, transport=self._transport
                ) as client:
                    response = await client.post(
                        f"{_ENDPOINT}/{choice.model}:generateContent",
                        headers={
                            "x-goog-api-key": choice.credential.secret.get_secret_value(),
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
            except httpx.TimeoutException:
                raise AttemptFailure("TIMEOUT") from None
            except httpx.RequestError:
                raise AttemptFailure("NETWORK") from None
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if response.status_code != 200:
                raise classify_failure(
                    response.status_code, payload, response.headers.get("Retry-After")
                )
            try:
                candidate = payload["candidates"][0]
                finish = candidate.get("finishReason", "STOP")
                if finish in {
                    "SAFETY",
                    "PROHIBITED_CONTENT",
                    "BLOCKLIST",
                    "RECITATION",
                }:
                    raise AttemptFailure("RESTRICTED", scope="fatal")
                if finish != "STOP":
                    raise ValueError()
                parts = candidate["content"]["parts"]
                raw = "".join(
                    part["text"]
                    for part in parts
                    if "text" in part and not part.get("thought")
                ).strip()
                if not raw:
                    raise ValueError()
                data = parse(raw) if parse else raw
            except AttemptFailure:
                raise
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                feedback = (
                    payload.get("promptFeedback", {})
                    if isinstance(payload, dict)
                    else {}
                )
                if isinstance(feedback, dict) and feedback.get("blockReason"):
                    raise AttemptFailure("RESTRICTED", scope="fatal") from None
                raise AttemptFailure("OUTPUT_INVALID") from None
            usage = payload.get("usageMetadata", {})
            if not isinstance(usage, dict):
                usage = {}

            def count(name):
                value = usage.get(name)
                return value if isinstance(value, int) and value >= 0 else None

            output = count("candidatesTokenCount")
            thoughts = count("thoughtsTokenCount")
            return Payload(
                data,
                payload.get("modelVersion"),
                count("promptTokenCount"),
                (output or 0) + (thoughts or 0)
                if output is not None or thoughts is not None
                else None,
                count("totalTokenCount"),
            )

        try:
            return await self.manager.run_async(
                task, model, send, timeout=timeout, legacy=["gemini-3.1-flash-lite"]
            )
        except PoolUnavailable as error:
            if error.reason == "INVALID_REQUEST":
                raise AIOutputValidationError(
                    "Gemini rejected the request parameters."
                ) from None
            if error.reason == "RESTRICTED":
                raise AIOutputValidationError(
                    "Gemini could not process this content."
                ) from None
            if error.last_kind in {"QUOTA", "DAILY_QUOTA"}:
                raise AIRateLimitError() from None
            if error.last_kind == "TIMEOUT" or error.reason == "DEADLINE":
                raise AITimeoutError() from None
            if error.last_kind in {"AUTH", "PERMISSION", "MODEL_UNAVAILABLE"}:
                raise AIConfigurationError(
                    "No configured Gemini credential/model is accessible."
                ) from None
            if error.last_kind == "OUTPUT_INVALID":
                raise AIOutputValidationError() from None
            raise AIServiceUnavailableError() from None

    async def generate_for_task(
        self,
        task_type,
        messages,
        model,
        *,
        temperature=0.7,
        max_tokens=None,
        timeout=30,
    ):
        result = await self._request(
            messages,
            model,
            temperature=temperature,
            timeout=timeout,
            task=str(task_type),
            max_tokens=max_tokens,
        )
        return replace(
            result,
            data=AIResponse(
                content=result.data,
                model=result.model,
                tier=AIRoutingTier.FAST,
                tokens_used=result.total_tokens,
            ),
        )

    async def generate_structured_for_task(
        self, task_type, messages, schema, model, *, temperature=0.2, timeout=30
    ):
        return await self._request(
            messages,
            model,
            temperature=temperature,
            timeout=timeout,
            json_mode=True,
            response_schema=schema.model_json_schema(),
            task=str(task_type),
            parse=schema.model_validate_json,
        )

    async def generate(
        self,
        messages: list[AIMessage],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 30.0,
    ) -> AIResponse:
        return (
            await self.generate_for_task(
                "DEFAULT",
                messages,
                model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        ).data

    async def generate_structured(
        self,
        messages: list[AIMessage],
        schema: type[T],
        model: str,
        *,
        temperature: float = 0.2,
        timeout: float = 30.0,
    ) -> T:
        return (
            await self.generate_structured_for_task(
                "DEFAULT",
                messages,
                schema,
                model,
                temperature=temperature,
                timeout=timeout,
            )
        ).data

    async def stream(
        self,
        messages: list[AIMessage],
        model: str,
        *,
        temperature: float = 0.7,
        timeout: float = 30.0,
    ) -> AsyncIterator[str]:
        raise AIConfigurationError(
            "Gemini streaming is not configured for this provider."
        )
        yield ""  # pragma: no cover

    async def embed(
        self, texts: list[str], model: str, *, timeout: float = 30.0
    ) -> list[list[float]]:
        raise AIConfigurationError(
            "Gemini embeddings are not configured for this provider."
        )
