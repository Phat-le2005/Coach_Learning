from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role, require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.learning.schemas import (
    QuickCheckResultRead,
    QuickCheckStartRead,
    QuickCheckStartRequest,
)
from app.learning.service import QuickCheckService
from app.practice.schemas import PracticeAnswerCreate, QuestionAttemptRead
from app.users.models import Role, User

router = APIRouter(
    prefix="/learning",
    tags=["Learning Quick Check"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
StudentOrTeacherUser = Annotated[User, Depends(require_any_role(Role.STUDENT, Role.TEACHER))]
Database = Annotated[Session, Depends(get_db)]


def get_quick_check_service(session: Database) -> QuickCheckService:
    return QuickCheckService(session)


@router.post(
    "/quick-check/start",
    response_model=QuickCheckStartRead,
    status_code=http_status.HTTP_201_CREATED,
)
def start_quick_check(
    data: QuickCheckStartRequest,
    current_user: StudentUser,
    service: Annotated[QuickCheckService, Depends(get_quick_check_service)],
) -> QuickCheckStartRead:
    return service.start_quick_check(current_user, data)


@router.post(
    "/quick-check/{id}/answer",
    response_model=QuestionAttemptRead,
    status_code=http_status.HTTP_201_CREATED,
)
def answer_quick_check_question(
    id: UUID,
    data: PracticeAnswerCreate,
    current_user: StudentUser,
    service: Annotated[QuickCheckService, Depends(get_quick_check_service)],
) -> QuestionAttemptRead:
    return service.answer_question(current_user, id, data)


@router.get(
    "/quick-check/{id}/result",
    response_model=QuickCheckResultRead,
)
def get_quick_check_result(
    id: UUID,
    current_user: StudentOrTeacherUser,
    response: Response,
    service: Annotated[QuickCheckService, Depends(get_quick_check_service)],
) -> QuickCheckResultRead:
    response.headers["Cache-Control"] = "no-store"
    return service.get_result(current_user, id)
