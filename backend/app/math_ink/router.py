from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.math_ink.schemas import InkDocumentRead, InkPageRead, InkPageWrite, InkSaveRead
from app.math_ink.service import MathInkService
from app.users.models import Role, User

router = APIRouter(prefix="/math-solutions/attempts", tags=["Math Ink"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
               404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
               422: {"model": ErrorResponse}})
Student = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]
PageIndex = Annotated[int, Path(ge=0, le=29)]

@router.get("/{attempt_id}/ink", response_model=InkDocumentRead)
def get_document(attempt_id: UUID, current_user: Student, session: Database):
    return MathInkService(session).get_document(current_user.id, attempt_id)

@router.get("/{attempt_id}/ink/pages/{page_index}", response_model=InkPageRead)
def get_page(attempt_id: UUID, page_index: PageIndex, current_user: Student, session: Database):
    return MathInkService(session).get_page(current_user.id, attempt_id, page_index)

@router.put("/{attempt_id}/ink/pages/{page_index}", response_model=InkSaveRead)
def save_page(attempt_id: UUID, page_index: PageIndex, payload: InkPageWrite,
              current_user: Student, session: Database):
    return MathInkService(session).save_page(current_user.id, attempt_id, page_index, payload)
