from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.students.models import StudentProfile
from app.tutor.models import LearningMemoryType
from app.tutor.schemas import (
    StudentLearningMemoryRead,
    TutorSessionCreate,
    TutorSessionEndRequest,
    TutorSessionRead,
    TutorSessionSummaryRead,
)
from app.tutor.service import MemoryService, TutorSessionService
from app.users.models import Role, User

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Tutor & Learning Memory"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]
Gateway = Annotated[AIGateway, Depends(get_ai_gateway)]


def _get_student_profile(user: User, session: Session) -> StudentProfile:
    prof = session.execute(
        select(StudentProfile).where(StudentProfile.user_id == user.id)
    ).scalar_one_or_none()
    if not prof:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hồ sơ học sinh không tồn tại.",
        )
    return prof


# --------------------------------------------------------------------------
# Session Endpoints
# --------------------------------------------------------------------------

@router.post(
    "/tutor/sessions",
    response_model=TutorSessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Bắt đầu phiên gia sư AI mới",
)
def create_tutor_session(
    payload: TutorSessionCreate,
    current_user: StudentUser,
    session: Database,
) -> TutorSessionRead:
    prof = _get_student_profile(current_user, session)
    service = TutorSessionService(session)
    t_session = service.create_session(student_id=prof.id, payload=payload)
    return TutorSessionRead.model_validate(t_session)


@router.post(
    "/tutor/sessions/{session_id}/turn",
    response_model=TutorSessionRead,
    summary="Ghi nhận thêm một lượt trao đổi trong phiên",
)
def record_session_turn(
    session_id: UUID,
    current_user: StudentUser,
    session: Database,
) -> TutorSessionRead:
    prof = _get_student_profile(current_user, session)
    service = TutorSessionService(session)
    t_session = service.record_turn(session_id)
    if not t_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên học không tồn tại hoặc đã kết thúc.",
        )
    if t_session.student_id != prof.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền truy cập phiên học của học sinh khác.",
        )
    return TutorSessionRead.model_validate(t_session)


@router.post(
    "/tutor/sessions/{session_id}/end",
    response_model=TutorSessionSummaryRead,
    summary="Kết thúc phiên học và trích xuất ký ức học tập",
)
async def end_tutor_session(
    session_id: UUID,
    payload: TutorSessionEndRequest | None,
    current_user: StudentUser,
    session: Database,
    gateway: Gateway,
) -> TutorSessionSummaryRead:
    prof = _get_student_profile(current_user, session)
    service = TutorSessionService(session)
    try:
        t_session, summary, memories = await service.end_session_async(
            session_id=session_id,
            student_id=prof.id,
            req=payload,
            gateway=gateway,
        )
    except ApplicationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return TutorSessionSummaryRead.model_validate(summary)


# --------------------------------------------------------------------------
# Learning Memory Endpoints
# --------------------------------------------------------------------------

@router.get(
    "/students/me/learning-memories",
    response_model=list[StudentLearningMemoryRead],
    summary="Xem các ký ức học tập dài hạn của học sinh",
)
def get_my_learning_memories(
    current_user: StudentUser,
    session: Database,
    type: LearningMemoryType | None = Query(default=None, description="Lọc theo loại ký ức"),
) -> list[StudentLearningMemoryRead]:
    prof = _get_student_profile(current_user, session)
    service = MemoryService(session)
    memories = service.list_memories(student_id=prof.id, memory_type=type)
    return [StudentLearningMemoryRead.model_validate(m) for m in memories]


@router.delete(
    "/students/me/learning-memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa hoặc hủy kích hoạt một ký ức học tập",
)
def delete_my_learning_memory(
    memory_id: UUID,
    current_user: StudentUser,
    session: Database,
) -> None:
    prof = _get_student_profile(current_user, session)
    service = MemoryService(session)
    success = service.delete_memory(student_id=prof.id, memory_id=memory_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ký ức học tập không tồn tại hoặc không thuộc về bạn.",
        )
