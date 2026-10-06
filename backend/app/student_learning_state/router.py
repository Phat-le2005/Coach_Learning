from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.student_learning_state.schemas import StudentLearningStateRead
from app.student_learning_state.service import StudentLearningStateService
from app.students.models import StudentProfile
from app.users.models import Role, User

router = APIRouter(
    prefix="/students/me",
    tags=["Student learning state"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]


@router.get("/learning-state", response_model=StudentLearningStateRead)
def get_learning_state(
    user: StudentUser,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    subject_id: Annotated[UUID | None, Query()] = None,
) -> StudentLearningStateRead:
    response.headers["Cache-Control"] = "no-store"

    profile = session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == user.id)
    )
    if profile is None:
        raise ApplicationError(
            404, "STUDENT_PROFILE_NOT_FOUND", "Student profile was not found."
        )

    service = StudentLearningStateService(session)
    return service.get_learning_state(profile.id, subject_id=subject_id)
