from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.parents.dashboard_schemas import (
    ParentStudentProgressRead,
    ParentStudentSummaryRead,
    ParentWeeklyAISummaryRead,
    ParentWeeklyDataRead,
)
from app.parents.dashboard_service import ParentDashboardService
from app.parents.parent_ai_service import ParentAISummaryService
from app.users.models import Role, User

router = APIRouter(
    prefix="/parent",
    tags=["Parent Portal"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)

ParentUser = Annotated[User, Depends(require_role(Role.PARENT))]


def get_dashboard_service(session: Annotated[Session, Depends(get_db)]) -> ParentDashboardService:
    return ParentDashboardService(session)


def get_ai_summary_service(session: Annotated[Session, Depends(get_db)]) -> ParentAISummaryService:
    return ParentAISummaryService(session)


@router.get(
    "/students",
    response_model=list[ParentStudentSummaryRead],
    summary="List linked students for the authenticated parent",
)
def get_linked_students(
    user: ParentUser,
    service: Annotated[ParentDashboardService, Depends(get_dashboard_service)],
) -> list[ParentStudentSummaryRead]:
    return service.get_linked_students(user.id)


@router.get(
    "/students/{student_id}/progress",
    response_model=ParentStudentProgressRead,
    summary="Get aggregated academic progress of a linked student",
)
def get_student_progress(
    student_id: UUID,
    user: ParentUser,
    service: Annotated[ParentDashboardService, Depends(get_dashboard_service)],
) -> ParentStudentProgressRead:
    return service.get_student_progress(user.id, student_id)


@router.get(
    "/students/{student_id}/weekly-data",
    response_model=ParentWeeklyDataRead,
    summary="Get detailed weekly study time and daily breakdown for a linked student",
)
def get_student_weekly_data(
    student_id: UUID,
    user: ParentUser,
    service: Annotated[ParentDashboardService, Depends(get_dashboard_service)],
    target_date: Annotated[date | None, Query(description="Target date within the desired week")] = None,
) -> ParentWeeklyDataRead:
    return service.get_student_weekly_data(user.id, student_id, target_date)


@router.post(
    "/students/{student_id}/ai-summary",
    response_model=ParentWeeklyAISummaryRead,
    summary="Generate pedagogical AI weekly summary for a linked student",
)
def generate_student_ai_summary(
    student_id: UUID,
    user: ParentUser,
    service: Annotated[ParentAISummaryService, Depends(get_ai_summary_service)],
    target_date: Annotated[date | None, Query(description="Target date within the desired week")] = None,
) -> ParentWeeklyAISummaryRead:
    return service.generate_weekly_summary(user.id, student_id, target_date)


parents_alias_router = APIRouter(
    prefix="/parents",
    tags=["Parent Portal"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)


@parents_alias_router.get(
    "/students",
    response_model=list[ParentStudentSummaryRead],
    include_in_schema=False,
)
def get_linked_students_alias(
    user: ParentUser,
    service: Annotated[ParentDashboardService, Depends(get_dashboard_service)],
) -> list[ParentStudentSummaryRead]:
    return service.get_linked_students(user.id)


@parents_alias_router.get(
    "/students/{student_id}/progress",
    response_model=ParentStudentProgressRead,
    include_in_schema=False,
)
def get_student_progress_alias(
    student_id: UUID,
    user: ParentUser,
    service: Annotated[ParentDashboardService, Depends(get_dashboard_service)],
) -> ParentStudentProgressRead:
    return service.get_student_progress(user.id, student_id)


@parents_alias_router.get(
    "/students/{student_id}/weekly-data",
    response_model=ParentWeeklyDataRead,
    include_in_schema=False,
)
def get_student_weekly_data_alias(
    student_id: UUID,
    user: ParentUser,
    service: Annotated[ParentDashboardService, Depends(get_dashboard_service)],
    target_date: Annotated[date | None, Query(description="Target date within the desired week")] = None,
) -> ParentWeeklyDataRead:
    return service.get_student_weekly_data(user.id, student_id, target_date)


@parents_alias_router.post(
    "/students/{student_id}/ai-summary",
    response_model=ParentWeeklyAISummaryRead,
    include_in_schema=False,
)
def generate_student_ai_summary_alias(
    student_id: UUID,
    user: ParentUser,
    service: Annotated[ParentAISummaryService, Depends(get_ai_summary_service)],
    target_date: Annotated[date | None, Query(description="Target date within the desired week")] = None,
) -> ParentWeeklyAISummaryRead:
    return service.generate_weekly_summary(user.id, student_id, target_date)

