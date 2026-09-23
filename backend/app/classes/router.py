from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.classes.analytics_schemas import (
    ClassroomAlertsRead,
    ClassroomAnalyticsDashboardRead,
    ClassroomHeatmapRead,
    HeatmapView,
)
from app.classes.analytics_service import ClassAnalyticsService
from app.classes.copilot_schemas import TeacherCopilotRead, TeacherCopilotRequest
from app.classes.copilot_service import TeacherCopilotService
from app.classes.schemas import (
    ClassroomCreate,
    ClassroomStudentRead,
    StudentClassroomRead,
    StudentEnrollmentCreate,
    TeacherClassroomRead,
)
from app.classes.service import ClassroomService
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.users.models import Role, User

teacher_router = APIRouter(
    prefix="/teacher/classes",
    tags=["Teacher classrooms"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
student_router = APIRouter(
    prefix="/students/me/classes",
    tags=["Student classrooms"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]
StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]


def get_classroom_service(session: Annotated[Session, Depends(get_db)]) -> ClassroomService:
    return ClassroomService(session)


@teacher_router.post("", status_code=201, response_model=TeacherClassroomRead)
def create_classroom(
    data: ClassroomCreate,
    user: TeacherUser,
    service: Annotated[ClassroomService, Depends(get_classroom_service)],
) -> TeacherClassroomRead:
    return service.create_for_teacher(user.id, data)


@teacher_router.get("", response_model=list[TeacherClassroomRead])
def list_classrooms(
    user: TeacherUser,
    service: Annotated[ClassroomService, Depends(get_classroom_service)],
) -> list[TeacherClassroomRead]:
    return service.list_for_teacher(user.id)


@teacher_router.get("/{id}", response_model=TeacherClassroomRead)
def get_classroom(
    id: UUID,
    user: TeacherUser,
    service: Annotated[ClassroomService, Depends(get_classroom_service)],
) -> TeacherClassroomRead:
    return service.get_for_teacher(user.id, id)


@teacher_router.get("/{id}/students", response_model=list[ClassroomStudentRead])
def list_students(
    id: UUID,
    user: TeacherUser,
    service: Annotated[ClassroomService, Depends(get_classroom_service)],
) -> list[ClassroomStudentRead]:
    return service.list_students_for_teacher(user.id, id)


@teacher_router.post("/{id}/students", status_code=201, response_model=ClassroomStudentRead)
def enroll_student(
    id: UUID,
    data: StudentEnrollmentCreate,
    user: TeacherUser,
    service: Annotated[ClassroomService, Depends(get_classroom_service)],
) -> ClassroomStudentRead:
    return service.enroll_student(user.id, id, data)


def get_analytics_service(session: Annotated[Session, Depends(get_db)]) -> ClassAnalyticsService:
    return ClassAnalyticsService(session)


def get_copilot_service(
    session: Annotated[Session, Depends(get_db)],
    gateway: Annotated[AIGateway, Depends(get_ai_gateway)],
) -> TeacherCopilotService:
    return TeacherCopilotService(session=session, gateway=gateway)


@teacher_router.get("/{id}/analytics", response_model=ClassroomAnalyticsDashboardRead)
def get_classroom_analytics(
    id: UUID,
    user: TeacherUser,
    service: Annotated[ClassAnalyticsService, Depends(get_analytics_service)],
    include_synthetic: Annotated[bool, Query()] = False,
) -> ClassroomAnalyticsDashboardRead:
    return service.get_classroom_dashboard(user.id, id, include_synthetic=include_synthetic)


@teacher_router.get("/{id}/heatmap", response_model=ClassroomHeatmapRead)
def get_classroom_heatmap(
    id: UUID,
    user: TeacherUser,
    service: Annotated[ClassAnalyticsService, Depends(get_analytics_service)],
    view: Annotated[HeatmapView, Query()] = HeatmapView.PROBLEM_TYPE,
    subject_id: Annotated[UUID | None, Query()] = None,
    include_synthetic: Annotated[bool, Query()] = False,
) -> ClassroomHeatmapRead:
    return service.get_classroom_heatmap(
        user.id,
        id,
        view=view,
        subject_id=subject_id,
        include_synthetic=include_synthetic,
    )


@teacher_router.get("/{id}/alerts", response_model=ClassroomAlertsRead)
def get_classroom_alerts(
    id: UUID,
    user: TeacherUser,
    service: Annotated[ClassAnalyticsService, Depends(get_analytics_service)],
    include_synthetic: Annotated[bool, Query()] = False,
) -> ClassroomAlertsRead:
    return service.get_classroom_alerts(user.id, id, include_synthetic=include_synthetic)


@teacher_router.post("/{id}/copilot", response_model=TeacherCopilotRead)
def consult_teacher_copilot(
    id: UUID,
    user: TeacherUser,
    request: TeacherCopilotRequest,
    service: Annotated[TeacherCopilotService, Depends(get_copilot_service)],
) -> TeacherCopilotRead:
    return service.consult_copilot(user.id, id, request)


@student_router.get("", response_model=list[StudentClassroomRead])
def list_my_classrooms(
    user: StudentUser,
    service: Annotated[ClassroomService, Depends(get_classroom_service)],
) -> list[StudentClassroomRead]:
    return service.list_for_student(user.id)
