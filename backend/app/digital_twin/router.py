from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.digital_twin.schemas import StudentDigitalTwinSnapshot
from app.digital_twin.service import StudentDigitalTwinService
from app.users.models import Role, User

router = APIRouter(
    tags=["Student Digital Twin"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]
Database = Annotated[Session, Depends(get_db)]


@router.get("/students/me/digital-twin", response_model=StudentDigitalTwinSnapshot)
def get_my_digital_twin(
    current_user: StudentUser, session: Database, response: Response
) -> StudentDigitalTwinSnapshot:
    response.headers["Cache-Control"] = "no-store"
    return StudentDigitalTwinService(session).get_snapshot_for_user(current_user.id)


@router.get(
    "/teacher/students/{student_id}/digital-twin",
    response_model=StudentDigitalTwinSnapshot,
)
def get_student_digital_twin_for_teacher(
    student_id: UUID,
    current_user: TeacherUser,
    session: Database,
    response: Response,
) -> StudentDigitalTwinSnapshot:
    response.headers["Cache-Control"] = "no-store"
    return StudentDigitalTwinService(session).get_snapshot_for_teacher(
        current_user.id, student_id
    )

