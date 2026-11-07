"""Gemini REST provider. Keys stay server-side; provider failures never synthesize grades."""

from collections.abc import AsyncIterator
import json
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.ai.exceptions import (
    AIConfigurationError, AIOutputValidationError, AIRateLimitError,
    AIServiceUnavailableError, AITimeoutError,
)
from app.ai.provider import AIProvider
from app.ai.types import AIMessage, AIResponse, AIRoutingTier

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
            if k in (
                "$defs", "definitions", "title", "description", "default",
                "additionalProperties", "minLength", "maxLength", "pattern",
                "minItems", "maxItems", "minimum", "maximum",
            ):
                continue
            if k == "anyOf":
                non_null = [item for item in v if isinstance(item, dict) and item.get("type") != "null"]
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

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not api_key.strip():
            raise AIConfigurationError("Gemini API key is not configured.")
        self._api_key = api_key
        self._transport = transport

    async def _request(
        self, messages: list[AIMessage], model: str, *, temperature: float,
        timeout: float, json_mode: bool = False, response_schema: dict | None = None,
    ) -> str:
        if not _MODEL_ID.fullmatch(model):
            raise AIConfigurationError("Invalid Gemini model identifier.")
        system_text = "\n".join(m.content for m in messages if str(m.role) == "system")
        contents = [
            {"role": "model" if str(m.role) == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages if str(m.role) != "system"
        ]
        if not contents:
            raise AIConfigurationError("Gemini request has no user content.")
        body: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}
        if json_mode:
            body["generationConfig"] = {"temperature": temperature, "responseMimeType": "application/json"}
        if response_schema is not None:
            body["generationConfig"]["responseJsonSchema"] = _sanitize_schema_for_gemini(response_schema)
        
        models_to_try = [model]
        if model != "gemini-3.1-flash-lite":
            models_to_try.append("gemini-3.1-flash-lite")

        response = None
        for current_model in models_to_try:
            try:
                async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                    response = await client.post(
                        f"{_ENDPOINT}/{current_model}:generateContent",
                        headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                        json=body,
                    )
            except httpx.TimeoutException as exc:
                if current_model == models_to_try[-1]:
                    raise AITimeoutError("Gemini request timed out.") from exc
                continue
            except httpx.RequestError as exc:
                if current_model == models_to_try[-1]:
                    raise AIServiceUnavailableError("Gemini could not be reached.") from exc
                continue

            if response.status_code == 200:
                break
            if response.status_code in (503, 404, 400) and current_model != models_to_try[-1]:
                logger.warning(
                    "Gemini request for model %s returned %d (%s); falling back to %s",
                    current_model, response.status_code, response.text[:120], models_to_try[-1]
                )
                continue

        if response.status_code == 429:
            raise AIRateLimitError("Gemini quota is exhausted; try again later.")
        if response.status_code == 404:
            raise AIConfigurationError("Configured Gemini model is unavailable for this API key.")
        if response.status_code in (401, 403):
            raise AIConfigurationError("Gemini API key lacks access to the configured model.")
        if response.status_code != 200:
            raise AIServiceUnavailableError("Gemini request failed; no grade was recorded.")
        try:
            payload = response.json()
            parts = payload["candidates"][0]["content"]["parts"]
            result = "".join(part["text"] for part in parts if "text" in part and not part.get("thought")).strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIOutputValidationError("Gemini response contains no usable answer.") from exc
        if not result:
            raise AIOutputValidationError("Gemini response is empty.")
        return result

    async def generate(
        self, messages: list[AIMessage], model: str, *, temperature: float = 0.7,
        max_tokens: int | None = None, timeout: float = 30.0,
    ) -> AIResponse:
        content = await self._request(messages, model, temperature=temperature, timeout=timeout)
        return AIResponse(content=content, model=model, tier=AIRoutingTier.FAST)

    async def generate_structured(
        self, messages: list[AIMessage], schema: type[T], model: str, *,
        temperature: float = 0.2, timeout: float = 30.0,
    ) -> T:
        raw = await self._request(messages, model, temperature=temperature, timeout=timeout,
                                  json_mode=True, response_schema=schema.model_json_schema())
        try:
            return schema.model_validate_json(raw)
        except ValueError as exc:
            raise AIOutputValidationError("Gemini output failed the required schema; no grade was recorded.") from exc

    async def stream(
        self, messages: list[AIMessage], model: str, *, temperature: float = 0.7,
        timeout: float = 30.0,
    ) -> AsyncIterator[str]:
        raise AIConfigurationError("Gemini streaming is not configured for this provider.")
        yield ""  # pragma: no cover

    async def embed(self, texts: list[str], model: str, *, timeout: float = 30.0) -> list[list[float]]:
        raise AIConfigurationError("Gemini embeddings are not configured for this provider.")