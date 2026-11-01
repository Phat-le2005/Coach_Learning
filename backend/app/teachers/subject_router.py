"""Read-only subject choices for teacher material uploads (API v2)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.database.session import get_db
from app.subjects.models import Subject
from app.subjects.schemas import SubjectRead
from app.users.models import Role, User


router = APIRouter(prefix="/teacher", tags=["Teacher workspace"])
TeacherUser = Annotated[User, Depends(require_role(Role.TEACHER))]
Database = Annotated[Session, Depends(get_db)]


@router.get("/subjects", response_model=list[SubjectRead])
def list_teacher_subjects(_user: TeacherUser, session: Database) -> list[SubjectRead]:
    subjects = session.scalars(
        select(Subject).order_by(Subject.grade_level, Subject.order_index, Subject.name)
    ).all()
    return [SubjectRead.model_validate(subject) for subject in subjects]
