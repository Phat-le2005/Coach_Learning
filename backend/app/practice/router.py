from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.practice.schemas import (
    PracticeAnswerCreate,
    PracticeQuestionRead,
    PracticeSessionCreate,
    PracticeSessionRead,
    QuestionAttemptRead,
)
from app.practice.service import PracticeService
from app.users.models import Role, User

router = APIRouter(
    prefix="/practice",
    tags=["Practice"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "/sessions",
    response_model=PracticeSessionRead,
    status_code=http_status.HTTP_201_CREATED,
)
def create_practice_session(
    data: PracticeSessionCreate, current_user: StudentUser, session: Database
) -> PracticeSessionRead:
    service = PracticeService(session)
    return service.to_read(service.create_session(current_user, data))


@router.get("/sessions/{practice_session_id}", response_model=PracticeSessionRead)
def get_practice_session(
    practice_session_id: UUID, current_user: StudentUser, session: Database
) -> PracticeSessionRead:
    service = PracticeService(session)
    return service.to_read(service.get_session(current_user, practice_session_id))


@router.get(
    "/sessions/{practice_session_id}/next-question",
    response_model=PracticeQuestionRead,
)
def get_next_practice_question(
    practice_session_id: UUID, current_user: StudentUser, session: Database
) -> PracticeQuestionRead:
    question = PracticeService(session).get_next_question(current_user, practice_session_id)
    return PracticeQuestionRead.model_validate(question)


@router.post(
    "/sessions/{practice_session_id}/answer",
    response_model=QuestionAttemptRead,
    status_code=http_status.HTTP_201_CREATED,
)
def answer_practice_question(
    practice_session_id: UUID,
    data: PracticeAnswerCreate,
    current_user: StudentUser,
    session: Database,
) -> QuestionAttemptRead:
    attempt = PracticeService(session).answer(current_user, practice_session_id, data)
    return QuestionAttemptRead.model_validate(attempt)

