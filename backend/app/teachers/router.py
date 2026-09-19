from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.teachers.models import TeacherProfile
from app.teachers.schemas import TeacherProfilePatch, TeacherProfileRead
from app.teachers.service import TeacherProfileService
from app.users.models import Role, User

router = APIRouter(
    prefix="/teachers",
    tags=["Teachers"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]


def get_teacher_service(session: Annotated[Session, Depends(get_db)]) -> TeacherProfileService:
    return TeacherProfileService(session)


@router.get("/me", response_model=TeacherProfileRead)
def me(
    user: TeacherUser,
    response: Response,
    service: Annotated[TeacherProfileService, Depends(get_teacher_service)],
) -> TeacherProfile:
    response.headers["Cache-Control"] = "no-store"
    return service.get_for_user(user.id)


@router.patch("/me", response_model=TeacherProfileRead)
def update_me(
    data: TeacherProfilePatch,
    user: TeacherUser,
    response: Response,
    service: Annotated[TeacherProfileService, Depends(get_teacher_service)],
) -> TeacherProfile:
    response.headers["Cache-Control"] = "no-store"
    return service.update_for_user(user.id, data)
