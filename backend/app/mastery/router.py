from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.mastery.schemas import (
    ConceptMasteryRead,
    ProblemTypeMasteryRead,
    StudentMasteryRead,
)
from app.mastery.service import MasteryQueryService
from app.users.models import Role, User

router = APIRouter(
    tags=["Mastery"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]
Database = Annotated[Session, Depends(get_db)]


@router.get("/students/me/mastery", response_model=StudentMasteryRead)
def get_my_mastery(
    current_user: StudentUser, session: Database, response: Response
) -> StudentMasteryRead:
    response.headers["Cache-Control"] = "no-store"
    return MasteryQueryService(session).overview_for_student_user(current_user.id)


@router.get(
    "/students/me/mastery/problem-types/{problem_type_id}",
    response_model=ProblemTypeMasteryRead,
)
def get_my_problem_type_mastery(
    problem_type_id: UUID,
    current_user: StudentUser,
    session: Database,
    response: Response,
) -> ProblemTypeMasteryRead:
    response.headers["Cache-Control"] = "no-store"
    return MasteryQueryService(session).problem_type_for_student_user(
        current_user.id, problem_type_id
    )


@router.get(
    "/students/me/mastery/concepts/{concept_id}", response_model=ConceptMasteryRead
)
def get_my_concept_mastery(
    concept_id: UUID,
    current_user: StudentUser,
    session: Database,
    response: Response,
) -> ConceptMasteryRead:
    response.headers["Cache-Control"] = "no-store"
    return MasteryQueryService(session).concept_for_student_user(current_user.id, concept_id)


@router.get(
    "/teacher/students/{student_id}/mastery", response_model=StudentMasteryRead
)
def get_student_mastery_for_teacher(
    student_id: UUID,
    current_user: TeacherUser,
    session: Database,
    response: Response,
) -> StudentMasteryRead:
    response.headers["Cache-Control"] = "no-store"
    return MasteryQueryService(session).overview_for_teacher(current_user.id, student_id)

