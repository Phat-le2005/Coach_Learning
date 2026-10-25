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


@router.get("/attempts/{attempt_id}/ai-review", response_model=AIReviewAvailabilityRead)
def get_ai_review_availability(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(Role.STUDENT))],
    session: Annotated[Session, Depends(get_db)],
) -> AIReviewAvailabilityRead:
    MathSolutionService(session).get(current_user.id, attempt_id)
    attempt = session.get(SolutionAttempt, attempt_id)
    try:
        resolve_answer_reference(session, attempt, require_submitted=False)
    except ApplicationError as exc:
        if exc.code in {"GRADING_ANSWER_REQUIRED", "GRADING_SOURCE_MISMATCH", "GRADING_SOURCE_UNAVAILABLE"}:
            return AIReviewAvailabilityRead(available=False, reason_code=exc.code)
        raise
    return AIReviewAvailabilityRead(available=True)


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
    resolve_answer_reference(session, session.get(SolutionAttempt, attempt_id))
    limiter.check_rate_limit(
        current_user.id,
        minute_limit=settings.ai_rate_limit_per_minute,
        daily_limit=settings.ai_daily_requests_limit_per_student,
    )
    review = await AnswerGroundedAIService(session, gateway).review_attempt(attempt_id)
    return AIReviewRead(
        attempt_id=review.attempt_id,
        step_grades=[StepSuggestionRead(
            step_index=step.step_index, verdict=step.verdict, score=step.score,
            confidence=step.confidence, feedback=step.feedback,
        ) for step in review.step_grades],
        needs_teacher_review=review.needs_teacher_review,
    )