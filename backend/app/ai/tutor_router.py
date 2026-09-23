"""AI Tutor router — POST /ai/tutor

Supports streaming (text/plain SSE) and non-streaming (JSON) responses.
Only accessible to STUDENT role.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.ai.rate_limiter import require_ai_rate_limit
from app.ai.student_tutor_service import StudentTutorService
from app.ai.tutor_schemas import TutorRequest, TutorResponse
from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.users.models import Role, User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["AI Tutor"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]
Gateway = Annotated[AIGateway, Depends(get_ai_gateway)]


@router.post(
    "/tutor",
    response_model=None,
    dependencies=[Depends(require_ai_rate_limit)],
    summary="AI Socratic Tutor",
    description=(
        "Gửi câu hỏi / thắc mắc đến Gia sư AI. "
        "Tutor phản hồi theo phong cách Socratic — dẫn dắt học sinh tự khám phá, "
        "không đưa đáp án ngay. "
        "Đặt `stream=true` để nhận phản hồi dạng streaming text."
    ),
)
async def ai_tutor_endpoint(
    request: TutorRequest,
    current_user: StudentUser,
    session: Database,
    gateway: Gateway,
) -> TutorResponse | StreamingResponse:

    """POST /ai/tutor

    - `stream=false` (default): returns JSON `TutorResponse`.
    - `stream=true`: returns `StreamingResponse` with `text/plain; charset=utf-8`.
    """
    service = StudentTutorService(session)

    if request.stream:
        async def _generate():
            async for chunk in service.tutor_stream(
                student_user=current_user,
                gateway=gateway,
                request=request,
            ):
                yield chunk

        return StreamingResponse(
            _generate(),
            media_type="text/plain; charset=utf-8",
        )

    return await service.tutor(
        student_user=current_user,
        gateway=gateway,
        request=request,
    )
