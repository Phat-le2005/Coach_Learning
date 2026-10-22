from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.math_ocr.adapter import MathOCRAdapter
from app.math_ocr.dependencies import get_request_ocr_adapter
from app.math_ocr.schemas import OCRRecognizeRequest, OCRRecognizeResponse
from app.math_ocr.service import MathOCRService
from app.users.models import Role, User

router = APIRouter(
    prefix="/math-solutions/attempts",
    tags=["Math OCR"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

Student = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]
OCRAdapterDep = Annotated[MathOCRAdapter, Depends(get_request_ocr_adapter)]


@router.post("/{attempt_id}/ocr/recognize", response_model=OCRRecognizeResponse)
def recognize_strokes(
    attempt_id: UUID,
    payload: OCRRecognizeRequest,
    current_user: Student,
    session: Database,
    adapter: OCRAdapterDep,
) -> OCRRecognizeResponse:
    service = MathOCRService(session, adapter)
    return service.recognize_page_ink(current_user.id, attempt_id, payload)
