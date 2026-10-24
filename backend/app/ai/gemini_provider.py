"""Gemini REST provider. Keys stay server-side; provider failures never synthesize grades."""

from collections.abc import AsyncIterator
from base64 import b64encode
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


class GeminiProvider(AIProvider):
    """Use generateContent with JSON mode and strict local schema validation."""

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not api_key.strip():
            raise AIConfigurationError("Gemini API key is not configured.")
        self._api_key = api_key
        self._transport = transport

    async def _request(
        self, messages: list[AIMessage], model: str, *, temperature: float,
        timeout: float, json_mode: bool = False, image_bytes: bytes | None = None,
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
        if image_bytes is not None:
            contents[-1]["parts"].append({"inlineData": {"mimeType": "image/png", "data": b64encode(image_bytes).decode("ascii")}})
        body: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}
        if json_mode:
            body["generationConfig"] = {"temperature": temperature, "responseMimeType": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                response = await client.post(
                    f"{_ENDPOINT}/{model}:generateContent",
                    headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise AITimeoutError("Gemini request timed out.") from exc
        except httpx.RequestError as exc:
            raise AIServiceUnavailableError("Gemini could not be reached.") from exc
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
            result = "".join(part["text"] for part in parts if "text" in part).strip()
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
        schema_text = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        guided = [*messages, AIMessage(role="user", content=f"Return one JSON object matching this schema: {schema_text}")]
        raw = await self._request(guided, model, temperature=temperature, timeout=timeout, json_mode=True)
        try:
            return schema.model_validate_json(raw)
        except ValueError as exc:
            raise AIOutputValidationError("Gemini output failed the required schema; no grade was recorded.") from exc

    async def generate_image_structured(
        self, prompt: str, image_bytes: bytes, schema: type[T], model: str,
        *, timeout: float = 45.0,
    ) -> T:
        """Transcribe one PNG; the caller must treat output as an unverified suggestion."""
        schema_text = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        raw = await self._request(
            [AIMessage(role="user", content=f"{prompt}\nReturn JSON matching: {schema_text}")],
            model, temperature=0.0, timeout=timeout, json_mode=True, image_bytes=image_bytes,
        )
        try:
            return schema.model_validate_json(raw)
        except ValueError as exc:
            raise AIOutputValidationError("Gemini image transcription did not match the expected schema.") from exc

    async def stream(
        self, messages: list[AIMessage], model: str, *, temperature: float = 0.7,
        timeout: float = 30.0,
    ) -> AsyncIterator[str]:
        raise AIConfigurationError("Gemini streaming is not configured for this provider.")
        yield ""  # pragma: no cover

    async def embed(self, texts: list[str], model: str, *, timeout: float = 30.0) -> list[list[float]]:
        raise AIConfigurationError("Gemini embeddings are not configured for this provider.")