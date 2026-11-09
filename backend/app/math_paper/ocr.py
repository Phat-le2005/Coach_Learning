"""Untrusted, reviewable transcription of a student's uploaded paper.

This service never creates solution steps or grades. The student must compare
the suggestions with the retained original and confirm each step separately.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from io import BytesIO
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.ai.rate_limiter import AIRateLimiter
from app.core.config import Settings, get_settings
from app.ai.gemini_failover import (AttemptFailure, Payload, PoolUnavailable, classify_failure, get_gemini_manager)
from app.core.exceptions import ApplicationError
from app.math_paper.service import MathPaperService


_MODEL_ID = re.compile(r"^[a-zA-Z0-9._-]+$")
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
_REQUEST_BUDGET_SECONDS = 60.0
logger = logging.getLogger(__name__)


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
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None,
                 settings: Settings | None = None, manager=None) -> None:
        self.transport, self.settings, self.manager = transport, settings, manager

    async def transcribe(self, data: bytes, mime: str) -> PaperOcrOutput:
        settings = self.settings or get_settings()
        try:
            manager = self.manager or get_gemini_manager(settings)
        except PoolUnavailable:
            raise ApplicationError(503, "PAPER_OCR_NOT_CONFIGURED", "Gemini key pool configuration is invalid.") from None
        if settings.ai_provider.lower() != "gemini" or not manager.credentials:
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
            "generationConfig": {"responseMimeType": "application/json"},
        }

        async def send(choice, budget):
            try:
                async with httpx.AsyncClient(timeout=budget, transport=self.transport) as client:
                    response = await client.post(f"{_ENDPOINT}/{choice.model}:generateContent",
                        headers={"x-goog-api-key": choice.credential.secret.get_secret_value(),
                                 "Content-Type": "application/json"}, json=body)
            except httpx.TimeoutException:
                raise AttemptFailure('TIMEOUT') from None
            except httpx.RequestError:
                raise AttemptFailure('NETWORK') from None
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if response.status_code != 200:
                raise classify_failure(response.status_code, payload, response.headers.get('Retry-After'))
            try:
                candidate = payload['candidates'][0]
                finish = candidate.get('finishReason')
                if finish in {'SAFETY', 'PROHIBITED_CONTENT', 'BLOCKLIST', 'RECITATION'}:
                    raise AttemptFailure('RESTRICTED', scope='fatal')
                if finish != 'STOP':
                    raise ValueError()
                raw = ''.join(part['text'] for part in candidate['content']['parts']
                              if 'text' in part and not part.get('thought'))
                parsed = PaperOcrOutput.model_validate_json(raw)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                feedback = payload.get('promptFeedback', {}) if isinstance(payload, dict) else {}
                if isinstance(feedback, dict) and feedback.get('blockReason'):
                    raise AttemptFailure('RESTRICTED', scope='fatal') from None
                raise AttemptFailure('OUTPUT_INVALID') from None
            return Payload(parsed, payload.get('modelVersion'))

        try:
            return (await manager.run_async('OCR_PAPER_PDF' if mime == 'application/pdf' else 'OCR_PAPER', model, send,
                    timeout=min(_REQUEST_BUDGET_SECONDS, settings.gemini_ocr_total_timeout_seconds),
                    legacy=['gemini-3.1-flash-lite'])).data
        except PoolUnavailable as error:
            if error.reason == 'DEADLINE' or error.last_kind == 'TIMEOUT':
                code = 'PAPER_OCR_TIMEOUT'
            elif error.last_kind in {'QUOTA', 'DAILY_QUOTA'}:
                code = 'PAPER_OCR_RATE_LIMITED'
            elif error.last_kind in {'AUTH', 'PERMISSION', 'MODEL_UNAVAILABLE'}:
                code = 'PAPER_OCR_NOT_CONFIGURED'
            elif error.reason in {'INVALID_REQUEST', 'RESTRICTED'}:
                code = 'PAPER_OCR_REQUEST_REJECTED'
            elif error.last_kind == 'OUTPUT_INVALID':
                code = 'PAPER_OCR_INVALID'
            else:
                code = 'PAPER_OCR_UNAVAILABLE'
            raise ApplicationError(503, code, 'Paper recognition failed; no steps were saved.') from None


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
        sha = info["sha256"]
        mime = info["content_type"]
        page_count = len(PdfReader(BytesIO(data), strict=False).pages) if mime == "application/pdf" else 1
        if self.limiter is not None:
            settings = get_settings()
            self.limiter.check_rate_limit(actor_user_id,
                minute_limit=settings.ai_rate_limit_per_minute,
                daily_limit=settings.ai_daily_requests_limit_per_student)
        # Every explicit OCR request transcribes the original afresh. Never reuse
        # a previous transcription or send the reference answer to the provider.
        output = await self.transcriber.transcribe(data, mime)
        if any(suggestion.page_number > page_count for suggestion in output.suggestions):
            raise ApplicationError(503, "PAPER_OCR_INVALID", "OCR referenced a page that is not in the uploaded file.")
        return PaperOcrRead(paper_id=paper_id, file_sha256=sha, suggestions=output.suggestions)
