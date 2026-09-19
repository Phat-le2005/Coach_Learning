from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.subjects.models import Subject
from app.subjects.schemas import SubjectCreate, SubjectRead
from app.subjects.service import SubjectService
from app.users.models import Role

router = APIRouter(
    prefix="/admin/subjects",
    tags=["Admin subjects"],
    dependencies=[Depends(require_role(Role.ADMIN))],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)


def get_subject_service(session: Annotated[Session, Depends(get_db)]) -> SubjectService:
    return SubjectService(session)


@router.post("", status_code=201, response_model=SubjectRead)
def create_subject(
    data: SubjectCreate, service: Annotated[SubjectService, Depends(get_subject_service)]
) -> Subject:
    return service.create(data)


@router.get("", response_model=list[SubjectRead])
def list_subjects(
    service: Annotated[SubjectService, Depends(get_subject_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[Subject]:
    return service.list_subjects(offset=offset, limit=limit)
