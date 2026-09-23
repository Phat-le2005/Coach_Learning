from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.planning.study_explanation_schemas import StudyPlanExplanationRead
from app.planning.study_schemas import (
    StudyDayRead,
    StudyPlanRead,
    StudyPlanRecalculateRequest,
)
from app.planning.study_service import StudyPlanService
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


def get_study_plan_service(session: Annotated[Session, Depends(get_db)]) -> StudyPlanService:
    return StudyPlanService(session)


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


@router.get("/me/today", response_model=StudyDayRead)
def get_today_plan(
    user: StudentUser,
    response: Response,
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    plan_service: Annotated[StudyPlanService, Depends(get_study_plan_service)],
    include_explanation: Annotated[bool, Query()] = False,
) -> StudyDayRead:
    response.headers["Cache-Control"] = "no-store"
    student = student_service.get_for_user(user.id)
    return plan_service.get_today_plan(student.id, include_explanation=include_explanation)


@router.get("/me/today/explanation", response_model=StudyPlanExplanationRead)
def get_today_explanation(
    user: StudentUser,
    response: Response,
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    plan_service: Annotated[StudyPlanService, Depends(get_study_plan_service)],
) -> StudyPlanExplanationRead:
    response.headers["Cache-Control"] = "no-store"
    student = student_service.get_for_user(user.id)
    return plan_service.get_today_explanation(student.id)


@router.get("/me/study-plan", response_model=StudyPlanRead)
def get_study_plan(
    user: StudentUser,
    response: Response,
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    plan_service: Annotated[StudyPlanService, Depends(get_study_plan_service)],
) -> StudyPlanRead:
    response.headers["Cache-Control"] = "no-store"
    student = student_service.get_for_user(user.id)
    return plan_service.get_study_plan(student.id)


@router.post("/me/study-plan/recalculate", response_model=StudyPlanRead)
def recalculate_study_plan(
    user: StudentUser,
    response: Response,
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    plan_service: Annotated[StudyPlanService, Depends(get_study_plan_service)],
    data: StudyPlanRecalculateRequest | None = None,
) -> StudyPlanRead:
    response.headers["Cache-Control"] = "no-store"
    student = student_service.get_for_user(user.id)
    horizon_days = data.horizon_days if data else 7
    as_of = data.as_of if data else None
    return plan_service.recalculate_study_plan(student.id, as_of=as_of, horizon_days=horizon_days)

