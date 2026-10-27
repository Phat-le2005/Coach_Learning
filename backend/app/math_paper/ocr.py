"""Untrusted, reviewable transcription of a student's uploaded paper.

This service never creates solution steps or grades. The student must compare
the suggestions with the retained original and confirm each step separately.
"""

from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.ai.rate_limiter import AIRateLimiter
from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.math_paper.service import MathPaperService


_MODEL_ID = re.compile(r"^[a-zA-Z0-9._-]+$")
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


class PaperOcrSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1, le=30)
    kind: Literal["FORMULA", "TEXT", "TABLE"]
    text: str = Field(min_length=1, max_length=4000)
    uncertain: bool
    box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] 0-1000")


class PaperOcrOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[PaperOcrSuggestion] = Field(max_length=100)


class PaperOcrRead(PaperOcrOutput):
    paper_id: UUID
    file_sha256: str
    provider: Literal["GEMINI"] = "GEMINI"


_INSTRUCTIONS = (
    "You are transcribing a student's handwritten mathematics paper, not solving or grading it. "
    "Read only visible marks, in reading order, across every page. Split distinct solution steps "
    "into suggestions. Preserve mistakes exactly; never correct calculations or fill missing work. "
    "For each suggestion, provide its 2D bounding box as box_2d: [ymin, xmin, ymax, xmax] "
    "with coordinates normalized from 0 to 1000 integers. "
    "For variation/sign tables, use kind TABLE and transcribe visible row headings, values, signs "
    "and arrows in a compact multiline text representation. Never infer values hidden by a photo "
    "crop or unclear handwriting. Use [không rõ] for uncertain spans and set uncertain=true. "
    "Use page numbers starting at 1. Do not include the problem statement unless it is handwritten "
    "as part of the student's work. Return one JSON object matching the supplied schema."
)


class GeminiPaperTranscriber:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def transcribe(self, data: bytes, mime: str) -> PaperOcrOutput:
        settings = get_settings()
        if settings.ai_provider.lower() != "gemini" or not settings.ai_api_key.get_secret_value():
            raise ApplicationError(503, "PAPER_OCR_NOT_CONFIGURED", "Gemini OCR is not configured.")
        model = settings.ai_model_fast
        if not _MODEL_ID.fullmatch(model):
            raise ApplicationError(503, "PAPER_OCR_NOT_CONFIGURED", "Gemini model is invalid.")
        body = {
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}},
                {"text": "Transcribe this student's paper. JSON schema: " + json.dumps(
                    PaperOcrOutput.model_json_schema(), separators=(",", ":"), ensure_ascii=False,
                )},
            ]}],
            "systemInstruction": {"parts": [{"text": _INSTRUCTIONS}]},
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        try:
            async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
                response = await client.post(
                    f"{_ENDPOINT}/{model}:generateContent",
                    headers={"x-goog-api-key": settings.ai_api_key.get_secret_value(),
                             "Content-Type": "application/json"}, json=body,
                )
        except httpx.TimeoutException as exc:
            raise ApplicationError(503, "PAPER_OCR_TIMEOUT", "Paper recognition timed out. Try again.") from exc
        except httpx.RequestError as exc:
            raise ApplicationError(503, "PAPER_OCR_UNAVAILABLE", "Could not reach paper recognition.") from exc
        if response.status_code == 429:
            raise ApplicationError(503, "PAPER_OCR_RATE_LIMITED", "Gemini quota is currently exhausted.")
        if response.status_code in {401, 403, 404}:
            raise ApplicationError(503, "PAPER_OCR_NOT_CONFIGURED", "Gemini OCR configuration is unavailable.")
        if response.status_code != 200:
            raise ApplicationError(503, "PAPER_OCR_UNAVAILABLE", "Paper recognition failed; no steps were saved.")
        try:
            payload = response.json()
            if payload["candidates"][0].get("finishReason") != "STOP":
                raise ValueError("Truncated or blocked OCR response")
            raw = "".join(part["text"] for part in payload["candidates"][0]["content"]["parts"]
                           if "text" in part)
            return PaperOcrOutput.model_validate_json(raw)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ApplicationError(503, "PAPER_OCR_INVALID", "Paper recognition returned an invalid result; no steps were saved.") from exc


_CACHE_DIR = Path(__file__).resolve().parents[2] / "var"
_OCR_CACHE_FILE = _CACHE_DIR / "paper_ocr_cache.json"


def _load_ocr_cache_from_disk() -> dict[str, PaperOcrRead]:
    cache: dict[str, PaperOcrRead] = {}
    if not _OCR_CACHE_FILE.exists():
        return cache
    try:
        with open(_OCR_CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for item in raw:
            sha = item["file_sha256"]
            cache[sha] = PaperOcrRead.model_validate(item)
    except Exception:
        pass
    return cache


def _save_ocr_cache_to_disk(cache: dict[str, PaperOcrRead]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = [v.model_dump(mode="json") for v in cache.values()]
        with open(_OCR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_PAPER_OCR_CACHE: dict[str, PaperOcrRead] = _load_ocr_cache_from_disk()


class MathPaperOcrService:
    def __init__(self, session: Session, transcriber: GeminiPaperTranscriber | None = None,
                 limiter: AIRateLimiter | None = None) -> None:
        self.session = session
        self.transcriber = transcriber or GeminiPaperTranscriber()
        self.limiter = limiter

    async def recognize(self, actor_user_id: UUID, attempt_id: UUID, paper_id: UUID) -> PaperOcrRead:
        paper_service = MathPaperService(self.session)
        paper_service._attempt(actor_user_id, attempt_id, editable=True)
        info, data = paper_service.read(actor_user_id, attempt_id, paper_id)
        settings = get_settings()
        sha = info["sha256"]
        if settings.app_env != "test" and sha in _PAPER_OCR_CACHE:
            cached = _PAPER_OCR_CACHE[sha]
            return PaperOcrRead(paper_id=paper_id, file_sha256=sha, suggestions=cached.suggestions)

        mime = info["content_type"]
        page_count = len(PdfReader(BytesIO(data), strict=False).pages) if mime == "application/pdf" else 1
        if self.limiter is not None:
            settings = get_settings()
            self.limiter.check_rate_limit(actor_user_id,
                minute_limit=settings.ai_rate_limit_per_minute,
                daily_limit=settings.ai_daily_requests_limit_per_student)
        # The OCR input is the uploaded original only. The reference answer is never sent.
        output = await self.transcriber.transcribe(data, mime)
        if any(suggestion.page_number > page_count for suggestion in output.suggestions):
            raise ApplicationError(503, "PAPER_OCR_INVALID", "OCR referenced a page that is not in the uploaded file.")
        result = PaperOcrRead(paper_id=paper_id, file_sha256=sha, suggestions=output.suggestions)
        if settings.app_env != "test":
            _PAPER_OCR_CACHE[sha] = result
            _save_ocr_cache_to_disk(_PAPER_OCR_CACHE)
        return result
