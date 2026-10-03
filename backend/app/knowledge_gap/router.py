from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.knowledge_gap.root_cause import RootCauseDiagnosticService
from app.knowledge_gap.schemas import (
    RootCauseDiagnosisRead,
    RootCauseNextActionRead,
    RootCauseVerificationAnswerResult,
    RootCauseVerificationAnswerSubmit,
    RootCauseVerificationRead,
)
from app.knowledge_gap.target_resolver import VerifiedLearningTargetService
from app.knowledge_gap.verification import RootCauseVerificationService
from app.students.models import StudentProfile
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


def _require_student_profile_id(session: Session, user_id: UUID) -> UUID:
    student = session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == user_id)
    )
    if student is None:
        raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
    return student.id


@router.post(
    "/students/me/diagnostics/{diagnosis_id}/verification",
    response_model=RootCauseVerificationRead,
)
def start_diagnostic_verification(
    diagnosis_id: UUID,
    current_user: StudentUser,
    session: Database,
    response: Response,
) -> RootCauseVerificationRead:
    response.headers["Cache-Control"] = "no-store"
    student_id = _require_student_profile_id(session, current_user.id)
    service = RootCauseVerificationService(session)
    return service.start_verification(student_id, diagnosis_id)


@router.get(
    "/students/me/diagnostics/{diagnosis_id}/verification",
    response_model=RootCauseVerificationRead,
)
def get_diagnostic_verification(
    diagnosis_id: UUID,
    current_user: StudentUser,
    session: Database,
    response: Response,
) -> RootCauseVerificationRead:
    response.headers["Cache-Control"] = "no-store"
    student_id = _require_student_profile_id(session, current_user.id)
    service = RootCauseVerificationService(session)
    return service.get_verification(student_id, diagnosis_id)


@router.post(
    "/students/me/diagnostics/{diagnosis_id}/verification/items/{item_id}/answer",
    response_model=RootCauseVerificationAnswerResult,
)
def submit_verification_item_answer(
    diagnosis_id: UUID,
    item_id: UUID,
    data: RootCauseVerificationAnswerSubmit,
    current_user: StudentUser,
    session: Database,
    response: Response,
) -> RootCauseVerificationAnswerResult:
    response.headers["Cache-Control"] = "no-store"
    student_id = _require_student_profile_id(session, current_user.id)
    service = RootCauseVerificationService(session)
    return service.submit_verification_answer(student_id, diagnosis_id, item_id, data)


@router.get(
    "/students/me/diagnostics/{diagnosis_id}/next-action",
    response_model=RootCauseNextActionRead,
)
def get_diagnostic_next_action(
    diagnosis_id: UUID,
    current_user: StudentUser,
    session: Database,
    response: Response,
) -> RootCauseNextActionRead:
    response.headers["Cache-Control"] = "no-store"
    student_id = _require_student_profile_id(session, current_user.id)
    resolver = VerifiedLearningTargetService(session)
    return resolver.resolve_next_action(student_id, diagnosis_id)

