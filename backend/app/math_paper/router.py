"""Student-owned paper scans; OCR and grading require confirmed solution steps."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.ai.rate_limiter import AIRateLimiter, get_ai_rate_limiter
from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.math_paper.service import MAX_PAPER_BYTES, MathPaperService
from app.math_paper.ocr import MathPaperOcrService, PaperOcrRead
from app.users.models import Role, User


class PaperRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


router = APIRouter(prefix="/math-solutions/attempts", tags=["Math Paper"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
               404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
               422: {"model": ErrorResponse}, 429: {"model": ErrorResponse},
               503: {"model": ErrorResponse}})
Student = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]


@router.get("/{attempt_id}/paper", response_model=list[PaperRead])
def list_paper(attempt_id: UUID, current_user: Student, session: Database):
    return MathPaperService(session).list(current_user.id, attempt_id)


@router.post("/{attempt_id}/paper", response_model=PaperRead, status_code=status.HTTP_201_CREATED)
async def upload_paper(attempt_id: UUID, current_user: Student, session: Database,
                       file: Annotated[UploadFile, File()]):
    data = await file.read(MAX_PAPER_BYTES + 1)
    return MathPaperService(session).add(current_user.id, attempt_id, data,
        file.content_type, file.filename or "paper")


@router.get("/{attempt_id}/paper/{paper_id}")
def download_paper(attempt_id: UUID, paper_id: UUID, current_user: Student, session: Database):
    info, data = MathPaperService(session).read(current_user.id, attempt_id, paper_id)
    return Response(content=data, media_type=info["content_type"], headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox", "Content-Disposition": "inline",
    })


@router.post("/{attempt_id}/paper/{paper_id}", response_model=PaperOcrRead)
@router.post("/{attempt_id}/paper/{paper_id}/ocr", response_model=PaperOcrRead)
async def recognize_paper(attempt_id: UUID, paper_id: UUID, current_user: Student, session: Database,
                          limiter: Annotated[AIRateLimiter, Depends(get_ai_rate_limiter)]):
    return await MathPaperOcrService(session, limiter=limiter).recognize(current_user.id, attempt_id, paper_id)


@router.delete("/{attempt_id}/paper/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(attempt_id: UUID, paper_id: UUID, current_user: Student, session: Database):
    MathPaperService(session).delete(current_user.id, attempt_id, paper_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
