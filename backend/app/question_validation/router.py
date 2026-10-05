"""Admin-only API for acquisition candidate review and explicit draft promotion."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.database.session import get_db
from app.question_validation.models import QuestionValidationBatchStatus
from app.question_validation.promotion import QuestionValidationPromotionService
from app.question_validation.schemas import (
    BatchDetailRead,
    BatchRead,
    CandidateCreate,
    CandidatePatch,
    CandidateRead,
    CandidateRejectInput,
    ManualReviewInput,
)
from app.question_validation.service import QuestionValidationService
from app.questions.schemas import QuestionRead
from app.users.models import Role, User

router = APIRouter(
    prefix="/question-validation",
    tags=["question-validation"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)

Database = Annotated[Session, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]


@router.post(
    "/acquisition-requests/{request_id}/batches",
    response_model=BatchRead,
    status_code=http_status.HTTP_201_CREATED,
)
def create_validation_batch(
    request_id: UUID,
    response: Response,
    session: Database,
    current_user: AdminUser,
) -> BatchRead:
    response.headers["Cache-Control"] = "no-store"
    batch = QuestionValidationService(session).create_or_get_batch(
        request_id, created_by=current_user.id
    )
    return BatchRead.model_validate(batch)


@router.get("/batches", response_model=list[BatchRead])
def list_validation_batches(
    response: Response,
    session: Database,
    status: QuestionValidationBatchStatus | None = Query(default=None),
    acquisition_request_id: UUID | None = Query(default=None),
    subject_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[BatchRead]:
    response.headers["Cache-Control"] = "no-store"
    batches = QuestionValidationService(session).list_batches(
        status=status,
        acquisition_request_id=acquisition_request_id,
        subject_id=subject_id,
        offset=offset,
        limit=limit,
    )
    return [BatchRead.model_validate(batch) for batch in batches]


@router.get("/batches/{batch_id}", response_model=BatchDetailRead)
def get_validation_batch(
    batch_id: UUID, response: Response, session: Database
) -> BatchDetailRead:
    response.headers["Cache-Control"] = "no-store"
    return BatchDetailRead.model_validate(
        QuestionValidationService(session).get_batch(batch_id)
    )


@router.post(
    "/batches/{batch_id}/candidates",
    response_model=CandidateRead,
    status_code=http_status.HTTP_201_CREATED,
)
def create_validation_candidate(
    batch_id: UUID,
    payload: CandidateCreate,
    response: Response,
    session: Database,
    current_user: AdminUser,
) -> CandidateRead:
    response.headers["Cache-Control"] = "no-store"
    candidate = QuestionValidationService(session).create_candidate(
        batch_id, payload, created_by=current_user.id
    )
    return CandidateRead.model_validate(candidate)


@router.get("/candidates/{candidate_id}", response_model=CandidateRead)
def get_validation_candidate(
    candidate_id: UUID, response: Response, session: Database
) -> CandidateRead:
    response.headers["Cache-Control"] = "no-store"
    return CandidateRead.model_validate(
        QuestionValidationService(session).get_candidate(candidate_id)
    )


@router.patch("/candidates/{candidate_id}", response_model=CandidateRead)
def patch_validation_candidate(
    candidate_id: UUID,
    payload: CandidatePatch,
    response: Response,
    session: Database,
    current_user: AdminUser,
) -> CandidateRead:
    response.headers["Cache-Control"] = "no-store"
    candidate = QuestionValidationService(session).patch_candidate(
        candidate_id, payload, updated_by=current_user.id
    )
    return CandidateRead.model_validate(candidate)


@router.post("/candidates/{candidate_id}/validate", response_model=CandidateRead)
def validate_candidate(
    candidate_id: UUID, response: Response, session: Database
) -> CandidateRead:
    response.headers["Cache-Control"] = "no-store"
    return CandidateRead.model_validate(
        QuestionValidationService(session).run_system_validation(candidate_id)
    )


@router.post("/candidates/{candidate_id}/reviews", response_model=CandidateRead)
def review_candidate(
    candidate_id: UUID,
    payload: ManualReviewInput,
    response: Response,
    session: Database,
    current_user: AdminUser,
) -> CandidateRead:
    response.headers["Cache-Control"] = "no-store"
    return CandidateRead.model_validate(
        QuestionValidationService(session).record_manual_review(
            candidate_id, payload, checked_by=current_user.id
        )
    )


@router.post("/candidates/{candidate_id}/reject", response_model=CandidateRead)
def reject_candidate(
    candidate_id: UUID,
    payload: CandidateRejectInput,
    response: Response,
    session: Database,
    current_user: AdminUser,
) -> CandidateRead:
    response.headers["Cache-Control"] = "no-store"
    return CandidateRead.model_validate(
        QuestionValidationService(session).reject_candidate(
            candidate_id, payload, updated_by=current_user.id
        )
    )


@router.post("/candidates/{candidate_id}/promote", response_model=QuestionRead)
def promote_candidate(
    candidate_id: UUID,
    response: Response,
    session: Database,
    current_user: AdminUser,
) -> QuestionRead:
    response.headers["Cache-Control"] = "no-store"
    _, question = QuestionValidationPromotionService(session).promote(
        candidate_id, promoted_by=current_user.id
    )
    return QuestionRead.model_validate(question)
