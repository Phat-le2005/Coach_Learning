from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.diagnostics.schemas import (
    DiagnosticAnswerCreate,
    DiagnosticAnswerRead,
    DiagnosticQuestionRead,
    DiagnosticResultRead,
    DiagnosticStartCreate,
    DiagnosticStartRead,
)
from app.diagnostics.service import DiagnosticService
from app.users.models import Role, User

router = APIRouter(
    prefix="/diagnostic",
    tags=["Diagnostic"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "/start",
    response_model=DiagnosticStartRead,
    status_code=http_status.HTTP_201_CREATED,
)
def start_diagnostic(
    data: DiagnosticStartCreate,
    current_user: StudentUser,
    session: Database,
) -> DiagnosticStartRead:
    return DiagnosticService(session).start(current_user, data)


@router.get("/{diagnostic_id}/next", response_model=DiagnosticQuestionRead)
def next_diagnostic_question(
    diagnostic_id: UUID,
    current_user: StudentUser,
    session: Database,
) -> DiagnosticQuestionRead:
    return DiagnosticService(session).next_question(current_user, diagnostic_id)


@router.post(
    "/{diagnostic_id}/answer",
    response_model=DiagnosticAnswerRead,
    status_code=http_status.HTTP_201_CREATED,
)
def answer_diagnostic_question(
    diagnostic_id: UUID,
    data: DiagnosticAnswerCreate,
    current_user: StudentUser,
    session: Database,
) -> DiagnosticAnswerRead:
    return DiagnosticService(session).answer(current_user, diagnostic_id, data)


@router.get("/{diagnostic_id}/result", response_model=DiagnosticResultRead)
def get_diagnostic_result(
    diagnostic_id: UUID,
    current_user: StudentUser,
    session: Database,
) -> DiagnosticResultRead:
    return DiagnosticService(session).result(current_user, diagnostic_id)
