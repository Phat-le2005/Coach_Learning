"""Teacher Grading Review Queue, Batch Approval, and Override endpoints (API v2)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.math_solutions.teacher_grading_schemas import (
    AttemptGradingDetail,
    BatchApproveRequest,
    BatchApproveResponse,
    PaginatedGradingQueue,
    RetrySyncResponse,
    TeacherOverrideRequest,
    TeacherOverrideResponse,
)
from app.math_solutions.teacher_grading_service import TeacherGradingService
from app.users.models import Role, User


def _disable_grading_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(
    prefix="/teacher/grading",
    tags=["Teacher Grading"],
    dependencies=[Depends(_disable_grading_caching)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]
Database = Annotated[Session, Depends(get_db)]


@router.get("/queue", response_model=PaginatedGradingQueue)
def list_grading_queue(
    teacher: TeacherUser,
    session: Database,
    classroom_id: UUID | None = None,
    assignment_id: UUID | None = None,
    status: str | None = Query(default="PENDING"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedGradingQueue:
    return TeacherGradingService(session).list_queue(
        teacher.id,
        classroom_id=classroom_id,
        assignment_id=assignment_id,
        status_filter=status,
        page=page,
        size=size,
    )


@router.get("/attempts/{attempt_id}", response_model=AttemptGradingDetail)
def get_attempt_detail(
    attempt_id: UUID,
    teacher: TeacherUser,
    session: Database,
) -> AttemptGradingDetail:
    return TeacherGradingService(session).get_attempt_detail(teacher.id, attempt_id)


@router.post("/batch-approve", response_model=BatchApproveResponse, status_code=status.HTTP_200_OK)
def batch_approve(
    data: BatchApproveRequest,
    teacher: TeacherUser,
    session: Database,
) -> BatchApproveResponse:
    return TeacherGradingService(session).batch_approve(teacher.id, data)


@router.post("/{attempt_id}/override", response_model=TeacherOverrideResponse, status_code=status.HTTP_200_OK)
def override_attempt(
    attempt_id: UUID,
    data: TeacherOverrideRequest,
    teacher: TeacherUser,
    session: Database,
) -> TeacherOverrideResponse:
    return TeacherGradingService(session).override_attempt(teacher.id, attempt_id, data)


@router.post("/{attempt_id}/retry-sync", response_model=RetrySyncResponse, status_code=status.HTTP_200_OK)
def retry_sync(
    attempt_id: UUID,
    teacher: TeacherUser,
    session: Database,
) -> RetrySyncResponse:
    return TeacherGradingService(session).retry_sync(teacher.id, attempt_id)
