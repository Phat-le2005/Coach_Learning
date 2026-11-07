import asyncio
import json
import logging
from pathlib import Path
"""Student-owned hybrid step grading and provisional feedback API."""

logger = logging.getLogger(__name__)

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.exceptions import AIConfigurationError
from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.rate_limiter import AIRateLimiter, get_ai_rate_limiter
from app.auth.dependencies import get_auth_settings, require_role
from app.core.config import Settings
from app.core.errors import ErrorResponse
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.math_solutions.answer_grounded_ai import AnswerGroundedAIService, UnansweredAIService
from app.math_solutions.answer_reference import resolve_answer_reference
from app.math_solutions.assignment_grading import require_pending_assignment_item
from app.math_solutions.evaluator_service import MathEvaluatorService
from app.math_solutions.models import EvaluationDecision, SolutionAttempt, SolutionStep, StepEvaluation, StepRevision
from app.math_solutions.service import MathSolutionService
from app.users.models import Role, User


class StepSuggestionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_index: int = Field(ge=1)
    verdict: Literal["VALID", "INVALID", "NEEDS_REVIEW"]
    score: float | None = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    feedback: str
    error_nature: Literal["ARITHMETIC_SLIP", "CONSEQUENTIAL", "CONCEPTUAL"] | None = None


class AIReviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: UUID
    step_grades: list[StepSuggestionRead]
    needs_teacher_review: bool
    is_final: bool = False
    review_source: Literal["DETERMINISTIC", "TEACHER", "ANSWER_GROUNDED_AI", "UNANSWERED_AI"] = "ANSWER_GROUNDED_AI"
    final_score: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def enforce_grade_boundary(self) -> "AIReviewRead":
        trusted = self.review_source in {"DETERMINISTIC", "TEACHER"} or (
            self.review_source == "ANSWER_GROUNDED_AI" and self.is_final)
        if self.is_final != trusted or (self.final_score is not None) != trusted:
            raise ValueError("A final review requires a persisted grading decision.")
        if not trusted and any(step.score is not None for step in self.step_grades):
            raise ValueError("Provisional AI feedback cannot award step scores.")
        if self.is_final and self.review_source == "ANSWER_GROUNDED_AI" and (
            self.needs_teacher_review or not self.step_grades or any(
                step.score is None or step.verdict == "NEEDS_REVIEW" or step.confidence < .8
                for step in self.step_grades)):
            raise ValueError("A final Gemini grade requires complete verified step assessments.")
        if self.review_source == "UNANSWERED_AI" and (
            not self.needs_teacher_review or any(
                step.verdict != "NEEDS_REVIEW" or step.score is not None for step in self.step_grades
            )
        ):
            raise ValueError("Unanswered AI feedback cannot score steps.")
        return self


def get_step_ai_gateway(settings: Annotated[Settings, Depends(get_auth_settings)]) -> AIGateway | None:
    try:
        return get_ai_gateway_singleton(settings)
    except AIConfigurationError:
        # Missing Gemini credentials must not block the deterministic path.
        return None


router = APIRouter(
    prefix="/math-solutions",
    tags=["Math Step Review"],
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
_POLICY_VERSION = "hybrid-curated-rubric-v3"


def _review_key(attempt, reference):
    # Reopened/resubmitted work must not reuse feedback for older revisions.
    revision = getattr(attempt, "attempt_revision_number", 0)
    return (attempt.id, f"{_POLICY_VERSION}:{reference.content_sha256}:{revision}")


def _final_review(session: Session, attempt_id: UUID, decision: EvaluationDecision) -> AIReviewRead:
    """Read the persisted grade; never reconstruct a score from AI suggestions."""
    rows = session.execute(
        select(SolutionStep.step_index, StepEvaluation)
        .join(StepRevision, StepRevision.step_id == SolutionStep.id)
        .join(StepEvaluation, StepEvaluation.step_revision_id == StepRevision.id)
        .where(SolutionStep.attempt_id == attempt_id, SolutionStep.is_deleted.is_(False),
               StepEvaluation.rubric_id == decision.rubric_id)
        .order_by(SolutionStep.step_index, StepRevision.step_revision_number.desc())
    ).all()
    grades: dict[int, StepSuggestionRead] = {}
    gemini = False
    for index, evaluation in rows:
        if index in grades:
            continue
        verdict = evaluation.math_validity
        if verdict not in {"VALID", "INVALID"}:
            continue
        gemini = gemini or getattr(evaluation, "evaluator_type", "") == "GEMINI_REFERENCE"
        grades[index] = StepSuggestionRead(
            step_index=index, verdict=verdict, score=evaluation.score,
            confidence=evaluation.confidence,
            feedback=evaluation.error_description or "Bước giải đã được kiểm chứng bằng quy tắc toán học.",
        )
    return AIReviewRead(
        attempt_id=attempt_id, step_grades=list(grades.values()),
        needs_teacher_review=False, is_final=True,
        review_source=("TEACHER" if decision.decision_source != "AUTOMATED_CONSENSUS" else
                       "ANSWER_GROUNDED_AI" if gemini else "DETERMINISTIC"),
        final_score=decision.final_score,
    )


@router.get("/attempts/{attempt_id}/ai-review", response_model=AIReviewAvailabilityRead)
def get_ai_review_availability(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(Role.STUDENT))],
    session: Annotated[Session, Depends(get_db)],
) -> AIReviewAvailabilityRead:
    MathSolutionService(session).get(current_user.id, attempt_id)
    attempt = session.get(SolutionAttempt, attempt_id)
    decision = session.scalar(select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt_id))
    if decision is not None:
        return AIReviewAvailabilityRead(available=True, cached_review=_final_review(session, attempt_id, decision))
    try:
        ref = resolve_answer_reference(session, attempt, require_submitted=False, require_answer=False)
    except ApplicationError as exc:
        if exc.code in {"GRADING_SOURCE_MISMATCH", "GRADING_SOURCE_UNAVAILABLE"}:
            return AIReviewAvailabilityRead(available=False, reason_code=exc.code)
        raise
    if attempt.status == "SUBMITTED" and attempt.context_type == "CLASSROOM_ASSIGNMENT":
        try:
            require_pending_assignment_item(session, attempt)
        except ApplicationError as exc:
            if exc.code in {"GRADING_ASSIGNMENT_NOT_SUBMITTED", "GRADING_ASSIGNMENT_ITEM_NOT_PENDING",
                            "GRADING_ASSIGNMENT_ITEM_ALREADY_SCORED"}:
                return AIReviewAvailabilityRead(available=False, reason_code=exc.code)
            raise
    cached = _REVIEW_CACHE.get(_review_key(attempt, ref))
    return AIReviewAvailabilityRead(
        available=True,
        reason_code=None if ref.has_reviewed_reference else "PROVISIONAL_WITHOUT_ANSWER",
        cached_review=cached,
    )


_IN_FLIGHT_REVIEWS: dict[tuple[UUID, str], asyncio.Task[AIReviewRead]] = {}
_COALESCE_LOCK = asyncio.Lock()


@router.post("/attempts/{attempt_id}/ai-review", response_model=AIReviewRead)
async def review_submitted_steps(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(Role.STUDENT))],
    session: Annotated[Session, Depends(get_db)],
    gateway: Annotated[AIGateway | None, Depends(get_step_ai_gateway)],
    settings: Annotated[Settings, Depends(get_auth_settings)],
    limiter: Annotated[AIRateLimiter, Depends(get_ai_rate_limiter)],
) -> AIReviewRead:
    # Ownership and approved-source checks happen before any provider call.
    MathSolutionService(session).get(current_user.id, attempt_id)
    attempt = session.get(SolutionAttempt, attempt_id)
    decision = session.scalar(select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt_id))
    if decision is not None:
        return _final_review(session, attempt_id, decision)
    ref = resolve_answer_reference(session, attempt, require_answer=False)

    # Try deterministic grading first; unsupported mathematics goes to Gemini.
    # Reviewed PA2 criteria may produce a persisted grade after validation.
    if ref.has_reviewed_reference and attempt.rubric_id is not None:
        try:
            decision = MathEvaluatorService(session).evaluate_attempt(attempt_id)
        except ApplicationError as exc:
            if exc.code not in {
                "GRADING_RUBRIC_UNAVAILABLE", "GRADING_RUBRIC_UNSUPPORTED",
                "GRADING_TARGET_UNSUPPORTED", "GRADING_REVIEW_REQUIRED",
            }:
                raise
        else:
            return _final_review(session, attempt_id, decision)

    cache_key = _review_key(attempt, ref)

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
            if gateway is None or isinstance(gateway.provider, MockAIProvider):
                raise ApplicationError(503, "REAL_AI_PROVIDER_REQUIRED", "Gemini is required for provisional step feedback.")
            limiter.check_rate_limit(
                current_user.id,
                minute_limit=settings.ai_rate_limit_per_minute,
                daily_limit=settings.ai_daily_requests_limit_per_student,
            )
            async def _run() -> AIReviewRead:
                review = await (
                    AnswerGroundedAIService(session, gateway).review_attempt(attempt_id)
                    if ref.has_reviewed_reference else
                    UnansweredAIService(session, gateway).review_attempt(attempt_id)
                )
                if ref.has_reviewed_reference:
                    from app.math_solutions.curated_ai_grading import finalize_curated_ai_review
                    decision = finalize_curated_ai_review(session, attempt_id, review)
                    if decision is not None:
                        return _final_review(session, attempt_id, decision)
                # Preserve legacy backdrop eligibility: solution-only references
                # do not start writing mastery merely because they are readable.
                if ref.correct_answer and ref.allow_legacy_ai_backdrop:
                    # Granular Gating: An Answer-Grounded AI review updates student mastery and study plan
                    # as long as the review is not flagged for teacher review, and at least 50% of steps
                    # have a verified verdict with confidence >= 0.70.
                    verified_steps_count = sum(
                        1
                        for step in review.step_grades
                        if step.verdict in ("VALID", "INVALID")
                        and (step.confidence is None or step.confidence >= 0.70)
                    )
                    is_unverified = (
                        review.needs_teacher_review
                        or len(review.step_grades) == 0
                        or (verified_steps_count / max(1, len(review.step_grades)) < 0.50)
                    )
                    if is_unverified:
                        logger.info(
                            "Provisional AI review for attempt %s marked needs_teacher_review or has unverified steps; skipping mastery backdrop update.",
                            attempt_id,
                        )
                    else:
                        try:
                            from app.math_solutions.mastery_backdrop import MasteryBackdropService

                            MasteryBackdropService(session).record_answer_grounded_review(
                                attempt=attempt,
                                review=review,
                                content_sha256=ref.content_sha256,
                            )
                            if hasattr(session, "commit"):
                                session.commit()
                        except Exception as e:
                            if hasattr(session, "rollback"):
                                session.rollback()
                            logger.error(
                                "Failed to record verified answer-grounded review backdrop for attempt %s: %s",
                                attempt_id,
                                e,
                                exc_info=True,
                            )
                res = AIReviewRead(
                    attempt_id=review.attempt_id,
                    step_grades=[StepSuggestionRead(
                        step_index=step.step_index,
                        verdict=step.verdict,
                        score=None,
                        confidence=step.confidence,
                        feedback=step.feedback,
                        error_nature=getattr(step, "error_nature", None),
                    ) for step in review.step_grades],
                    needs_teacher_review=review.needs_teacher_review,
                    review_source="ANSWER_GROUNDED_AI" if ref.has_reviewed_reference else "UNANSWERED_AI",
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
