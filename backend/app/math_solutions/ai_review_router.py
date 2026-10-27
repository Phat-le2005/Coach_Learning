import asyncio
import json
from pathlib import Path
"""Student-owned, read-only Gemini step review API."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.gateway import AIGateway
from app.ai.rate_limiter import AIRateLimiter, get_ai_rate_limiter
from app.auth.dependencies import get_auth_settings, require_role
from app.core.config import Settings
from app.core.errors import ErrorResponse
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.math_solutions.answer_grounded_ai import AnswerGroundedAIService
from app.math_solutions.answer_reference import resolve_answer_reference
from app.math_solutions.models import SolutionAttempt
from app.math_solutions.service import MathSolutionService
from app.users.models import Role, User


class StepSuggestionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_index: int = Field(ge=1)
    verdict: Literal["VALID", "INVALID", "NEEDS_REVIEW"]
    score: float | None = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    feedback: str


class AIReviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: UUID
    step_grades: list[StepSuggestionRead]
    needs_teacher_review: bool
    is_final: Literal[False] = False


def get_step_ai_gateway(settings: Annotated[Settings, Depends(get_auth_settings)]) -> AIGateway:
    return get_ai_gateway_singleton(settings)


router = APIRouter(
    prefix="/math-solutions",
    tags=["Math AI Review"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
               404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
               422: {"model": ErrorResponse}, 429: {"model": ErrorResponse},
               503: {"model": ErrorResponse}},
)


class AIReviewAvailabilityRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: bool
    reason_code: str | None = None
    cached_review: AIReviewRead | None = None


_CACHE_DIR = Path(__file__).resolve().parents[2] / "var"
_CACHE_FILE = _CACHE_DIR / "ai_review_cache.json"


def _load_cache_from_disk() -> dict[tuple[UUID, str], AIReviewRead]:
    cache: dict[tuple[UUID, str], AIReviewRead] = {}
    if not _CACHE_FILE.exists():
        return cache
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for item in raw:
            aid = UUID(item["attempt_id"])
            sha = item["content_sha256"]
            review = AIReviewRead.model_validate(item["review"])
            cache[(aid, sha)] = review
    except Exception:
        pass
    return cache


def _save_cache_to_disk(cache: dict[tuple[UUID, str], AIReviewRead]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        items = [
            {
                "attempt_id": str(aid),
                "content_sha256": sha,
                "review": review.model_dump(mode="json"),
            }
            for (aid, sha), review in cache.items()
        ]
        tmp_file = _CACHE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        tmp_file.replace(_CACHE_FILE)
    except Exception:
        pass


_REVIEW_CACHE: dict[tuple[UUID, str], AIReviewRead] = _load_cache_from_disk()


@router.get("/attempts/{attempt_id}/ai-review", response_model=AIReviewAvailabilityRead)
def get_ai_review_availability(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(Role.STUDENT))],
    session: Annotated[Session, Depends(get_db)],
) -> AIReviewAvailabilityRead:
    MathSolutionService(session).get(current_user.id, attempt_id)
    attempt = session.get(SolutionAttempt, attempt_id)
    try:
        ref = resolve_answer_reference(session, attempt, require_submitted=False)
    except ApplicationError as exc:
        if exc.code in {"GRADING_ANSWER_REQUIRED", "GRADING_SOURCE_MISMATCH", "GRADING_SOURCE_UNAVAILABLE"}:
            return AIReviewAvailabilityRead(available=False, reason_code=exc.code)
        raise
    cached = _REVIEW_CACHE.get((attempt_id, ref.content_sha256))
    return AIReviewAvailabilityRead(available=True, cached_review=cached)


_IN_FLIGHT_REVIEWS: dict[tuple[UUID, str], asyncio.Task[AIReviewRead]] = {}
_COALESCE_LOCK = asyncio.Lock()


@router.post("/attempts/{attempt_id}/ai-review", response_model=AIReviewRead)
async def review_submitted_steps(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(Role.STUDENT))],
    session: Annotated[Session, Depends(get_db)],
    gateway: Annotated[AIGateway, Depends(get_step_ai_gateway)],
    settings: Annotated[Settings, Depends(get_auth_settings)],
    limiter: Annotated[AIRateLimiter, Depends(get_ai_rate_limiter)],
) -> AIReviewRead:
    # Ownership and trusted-answer checks happen before rate limiting or any provider call.
    MathSolutionService(session).get(current_user.id, attempt_id)
    ref = resolve_answer_reference(session, session.get(SolutionAttempt, attempt_id))
    limiter.check_rate_limit(
        current_user.id,
        minute_limit=settings.ai_rate_limit_per_minute,
        daily_limit=settings.ai_daily_requests_limit_per_student,
    )
    cache_key = (attempt_id, ref.content_sha256)

    # 1. Immediate cache hit: 0 latency, 0 Gemini call
    if cache_key in _REVIEW_CACHE:
        return _REVIEW_CACHE[cache_key]

    # 2. SingleFlight: coalesce concurrent in-flight requests into exactly one execution
    task: asyncio.Task[AIReviewRead] | None = None
    async with _COALESCE_LOCK:
        if cache_key in _REVIEW_CACHE:
            return _REVIEW_CACHE[cache_key]
        if cache_key in _IN_FLIGHT_REVIEWS:
            task = _IN_FLIGHT_REVIEWS[cache_key]
        else:
            async def _run() -> AIReviewRead:
                review = await AnswerGroundedAIService(session, gateway).review_attempt(attempt_id)
                res = AIReviewRead(
                    attempt_id=review.attempt_id,
                    step_grades=[StepSuggestionRead(
                        step_index=step.step_index, verdict=step.verdict, score=step.score,
                        confidence=step.confidence, feedback=step.feedback,
                    ) for step in review.step_grades],
                    needs_teacher_review=review.needs_teacher_review,
                )
                _REVIEW_CACHE[cache_key] = res
                _save_cache_to_disk(_REVIEW_CACHE)
                return res

            task = asyncio.create_task(_run())
            _IN_FLIGHT_REVIEWS[cache_key] = task

    try:
        return await asyncio.shield(task)
    finally:
        async with _COALESCE_LOCK:
            if _IN_FLIGHT_REVIEWS.get(cache_key) is task and task.done():
                _IN_FLIGHT_REVIEWS.pop(cache_key, None)