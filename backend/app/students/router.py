from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.students.models import StudentProfile
from app.students.schemas import StudentProfilePatch, StudentProfileRead
from app.students.service import StudentProfileService
from app.users.models import Role, User

router = APIRouter(
    prefix="/students",
    tags=["Students"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]


def get_student_service(session: Annotated[Session, Depends(get_db)]) -> StudentProfileService:
    return StudentProfileService(session)


@router.get("/me", response_model=StudentProfileRead)
def me(
    user: StudentUser,
    response: Response,
    service: Annotated[StudentProfileService, Depends(get_student_service)],
) -> StudentProfile:
    response.headers["Cache-Control"] = "no-store"
    return service.get_for_user(user.id)


@router.patch("/me", response_model=StudentProfileRead)
def update_me(
    data: StudentProfilePatch,
    user: StudentUser,
    response: Response,
    service: Annotated[StudentProfileService, Depends(get_student_service)],
) -> StudentProfile:
    response.headers["Cache-Control"] = "no-store"
    return service.update_for_user(user.id, data)
