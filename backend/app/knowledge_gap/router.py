from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.knowledge_gap.root_cause import RootCauseDiagnosticService
from app.knowledge_gap.schemas import RootCauseDiagnosisRead
from app.users.models import Role, User

router = APIRouter(
    tags=["Root Cause Diagnostics"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)

Database = Annotated[Session, Depends(get_db)]
StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]


@router.get(
    "/students/me/diagnostics/recent",
    response_model=list[RootCauseDiagnosisRead],
)
def recent_student_diagnostics(
    current_user: StudentUser,
    session: Database,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RootCauseDiagnosisRead]:
    response.headers["Cache-Control"] = "no-store"
    service = RootCauseDiagnosticService(session)
    rows = service.recent_for_student_user(current_user.id, limit=limit)
    return service.to_read_models(rows)


@router.get(
    "/students/me/diagnostics/{diagnosis_id}",
    response_model=RootCauseDiagnosisRead,
)
def student_diagnostic_detail(
    diagnosis_id: UUID,
    current_user: StudentUser,
    session: Database,
    response: Response,
) -> RootCauseDiagnosisRead:
    response.headers["Cache-Control"] = "no-store"
    service = RootCauseDiagnosticService(session)
    row = service.get_for_student_user(current_user.id, diagnosis_id)
    return service.to_read_model(row)


@router.get(
    "/teacher/students/{student_id}/diagnostics",
    response_model=list[RootCauseDiagnosisRead],
)
def teacher_student_diagnostics(
    student_id: UUID,
    current_user: TeacherUser,
    session: Database,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RootCauseDiagnosisRead]:
    response.headers["Cache-Control"] = "no-store"
    service = RootCauseDiagnosticService(session)
    rows = service.recent_for_teacher(current_user.id, student_id, limit=limit)
    return service.to_read_models(rows)
