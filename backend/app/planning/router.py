from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.planning.models import TeachingPlanStatus
from app.planning.schemas import TeachingPlanCreate, TeachingPlanPatch, TeachingPlanRead
from app.planning.service import TeachingPlanService
from app.users.models import Role, User

router = APIRouter(
    prefix="/teacher",
    tags=["Teaching plans"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]


def get_planning_service(session: Annotated[Session, Depends(get_db)]) -> TeachingPlanService:
    return TeachingPlanService(session)


@router.post(
    "/classes/{id}/teaching-plans",
    status_code=201,
    response_model=TeachingPlanRead,
)
def create_teaching_plan(
    id: UUID,
    data: TeachingPlanCreate,
    user: TeacherUser,
    service: Annotated[TeachingPlanService, Depends(get_planning_service)],
) -> TeachingPlanRead:
    return service.create_plan(user.id, id, data)


@router.get(
    "/classes/{id}/teaching-plans",
    response_model=list[TeachingPlanRead],
)
def list_teaching_plans(
    id: UUID,
    user: TeacherUser,
    response: Response,
    service: Annotated[TeachingPlanService, Depends(get_planning_service)],
    subject_id: Annotated[UUID | None, Query()] = None,
    status: Annotated[TeachingPlanStatus | None, Query()] = None,
) -> list[TeachingPlanRead]:
    response.headers["Cache-Control"] = "no-store"
    return service.list_plans(user.id, id, subject_id=subject_id, status=status)


@router.get(
    "/teaching-plans/{id}",
    response_model=TeachingPlanRead,
)
def get_teaching_plan(
    id: UUID,
    user: TeacherUser,
    response: Response,
    service: Annotated[TeachingPlanService, Depends(get_planning_service)],
) -> TeachingPlanRead:
    response.headers["Cache-Control"] = "no-store"
    return service.get_plan(user.id, id)


@router.patch(
    "/teaching-plans/{id}",
    response_model=TeachingPlanRead,
)
def patch_teaching_plan(
    id: UUID,
    data: TeachingPlanPatch,
    user: TeacherUser,
    service: Annotated[TeachingPlanService, Depends(get_planning_service)],
) -> TeachingPlanRead:
    return service.patch_plan(user.id, id, data)


@router.post(
    "/teaching-plans/{id}/activate",
    response_model=TeachingPlanRead,
)
def activate_teaching_plan(
    id: UUID,
    user: TeacherUser,
    service: Annotated[TeachingPlanService, Depends(get_planning_service)],
) -> TeachingPlanRead:
    return service.activate_plan(user.id, id)


@router.post(
    "/teaching-plans/{id}/complete",
    response_model=TeachingPlanRead,
)
def complete_teaching_plan(
    id: UUID,
    user: TeacherUser,
    service: Annotated[TeachingPlanService, Depends(get_planning_service)],
) -> TeachingPlanRead:
    return service.complete_plan(user.id, id)
