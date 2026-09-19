from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.parents.models import ParentProfile
from app.parents.schemas import ParentProfilePatch, ParentProfileRead
from app.parents.service import ParentProfileService
from app.users.models import Role, User

router = APIRouter(
    prefix="/parents",
    tags=["Parents"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
ParentUser = Annotated[User, Depends(require_role(Role.PARENT))]


def get_parent_service(session: Annotated[Session, Depends(get_db)]) -> ParentProfileService:
    return ParentProfileService(session)


@router.get("/me", response_model=ParentProfileRead)
def me(
    user: ParentUser,
    response: Response,
    service: Annotated[ParentProfileService, Depends(get_parent_service)],
) -> ParentProfile:
    response.headers["Cache-Control"] = "no-store"
    return service.get_for_user(user.id)


@router.patch("/me", response_model=ParentProfileRead)
def update_me(
    data: ParentProfilePatch,
    user: ParentUser,
    response: Response,
    service: Annotated[ParentProfileService, Depends(get_parent_service)],
) -> ParentProfile:
    response.headers["Cache-Control"] = "no-store"
    return service.update_for_user(user.id, data)
