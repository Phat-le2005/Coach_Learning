from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.students.goal_models import AcademicGoal, AcademicGoalStatus
from app.students.goal_schemas import AcademicGoalCreate, AcademicGoalPatch, AcademicGoalRead
from app.students.goal_service import AcademicGoalService
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


def get_academic_goal_service(session: Annotated[Session, Depends(get_db)]) -> AcademicGoalService:
    return AcademicGoalService(session)


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


@router.get("/me/goals", response_model=list[AcademicGoalRead])
def list_goals(
    user: StudentUser,
    response: Response,
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    goal_service: Annotated[AcademicGoalService, Depends(get_academic_goal_service)],
    status: AcademicGoalStatus | None = None,
) -> list[AcademicGoal]:
    response.headers["Cache-Control"] = "no-store"
    student = student_service.get_for_user(user.id)
    return goal_service.list_goals(student.id, status=status)


@router.post("/me/goals", response_model=AcademicGoalRead, status_code=201)
def create_goal(
    data: AcademicGoalCreate,
    user: StudentUser,
    response: Response,
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    goal_service: Annotated[AcademicGoalService, Depends(get_academic_goal_service)],
) -> AcademicGoal:
    response.headers["Cache-Control"] = "no-store"
    student = student_service.get_for_user(user.id)
    return goal_service.create_goal(student.id, data)


@router.patch("/me/goals/{id}", response_model=AcademicGoalRead)
def patch_goal(
    id: UUID,
    data: AcademicGoalPatch,
    user: StudentUser,
    response: Response,
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    goal_service: Annotated[AcademicGoalService, Depends(get_academic_goal_service)],
) -> AcademicGoal:
    response.headers["Cache-Control"] = "no-store"
    student = student_service.get_for_user(user.id)
    return goal_service.patch_goal(student.id, id, data)
