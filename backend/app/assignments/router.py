from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.assignments.schemas import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentSubmissionRequest,
    AssignmentSubmissionResultRead,
    MaterialItemGradeRequest,
    MaterialItemGradeRead,
    AssignmentSummaryRead,
    AssignmentUpdate,
    StudentAssignmentRead,
    TeacherAssignmentRosterRead,
)
from app.assignments.service import AssignmentService
from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.users.models import Role, User

teacher_router = APIRouter(
    prefix="/teacher",
    tags=["Teacher assignments"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

student_router = APIRouter(
    prefix="/students/me/assignments",
    tags=["Student assignments"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)

TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]
StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]


def get_assignment_service(session: Annotated[Session, Depends(get_db)]) -> AssignmentService:
    return AssignmentService(session)


# -------------------------------------------------------------------------
# Teacher Endpoints
# -------------------------------------------------------------------------

@teacher_router.post(
    "/classes/{classroom_id}/assignments",
    status_code=201,
    response_model=AssignmentRead,
)
def create_assignment(
    classroom_id: UUID,
    data: AssignmentCreate,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> AssignmentRead:
    if data.classroom_id != classroom_id:
        data = data.model_copy(update={"classroom_id": classroom_id})
    return service.create_assignment(user.id, data)


@teacher_router.get(
    "/classes/{classroom_id}/assignments",
    response_model=list[AssignmentSummaryRead],
)
def list_classroom_assignments(
    classroom_id: UUID,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> list[AssignmentSummaryRead]:
    return service.list_for_classroom(user.id, classroom_id)


@teacher_router.get(
    "/assignments/{assignment_id}",
    response_model=AssignmentRead,
)
def get_assignment_detail(
    assignment_id: UUID,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> AssignmentRead:
    return service.get_for_teacher(user.id, assignment_id)


@teacher_router.patch(
    "/assignments/{assignment_id}",
    response_model=AssignmentRead,
)
def update_assignment(
    assignment_id: UUID,
    data: AssignmentUpdate,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> AssignmentRead:
    return service.update_assignment(user.id, assignment_id, data)


@teacher_router.post(
    "/assignments/{assignment_id}/publish",
    response_model=AssignmentRead,
)
def publish_assignment(
    assignment_id: UUID,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> AssignmentRead:
    return service.publish_assignment(user.id, assignment_id)


@teacher_router.post(
    "/assignments/{assignment_id}/close",
    response_model=AssignmentRead,
)
def close_assignment(
    assignment_id: UUID,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> AssignmentRead:
    return service.close_assignment(user.id, assignment_id)


@teacher_router.get(
    "/assignments/{assignment_id}/submissions",
    response_model=TeacherAssignmentRosterRead,
)
def get_assignment_submissions(
    assignment_id: UUID,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> TeacherAssignmentRosterRead:
    return service.get_assignment_roster(user.id, assignment_id)


@teacher_router.post(
    "/assignments/{assignment_id}/students/{student_id}/material-items/{student_material_item_id}/grade",
    response_model=MaterialItemGradeRead,
)
def grade_material_item(
    assignment_id: UUID,
    student_id: UUID,
    student_material_item_id: UUID,
    data: MaterialItemGradeRequest,
    user: TeacherUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> MaterialItemGradeRead:
    return service.grade_material_item(
        user.id, assignment_id, student_id, student_material_item_id, data
    )


# -------------------------------------------------------------------------
# Student Endpoints
# -------------------------------------------------------------------------

@student_router.get(
    "",
    response_model=list[StudentAssignmentRead],
)
def list_student_assignments(
    user: StudentUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> list[StudentAssignmentRead]:
    return service.list_for_student(user.id)


@student_router.get(
    "/{assignment_id}",
    response_model=StudentAssignmentRead,
)
def get_student_assignment_detail(
    assignment_id: UUID,
    user: StudentUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> StudentAssignmentRead:
    return service.get_student_assignment(user.id, assignment_id)


@student_router.post(
    "/{assignment_id}/submit",
    response_model=AssignmentSubmissionResultRead,
)
def submit_student_assignment(
    assignment_id: UUID,
    submission: AssignmentSubmissionRequest,
    user: StudentUser,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> AssignmentSubmissionResultRead:
    return service.submit_assignment(user.id, assignment_id, submission)
