from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.auth.dependencies import require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.hints.schemas import HintRead, HintRequest
from app.hints.service import HintService
from app.users.models import Role, User

router = APIRouter(
    prefix="/practice/questions",
    tags=["Practice Hints"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)

StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
Database = Annotated[Session, Depends(get_db)]
Gateway = Annotated[AIGateway, Depends(get_ai_gateway)]


@router.post("/{question_id}/hint", response_model=HintRead)
async def request_practice_hint(
    question_id: UUID,
    data: HintRequest,
    current_user: StudentUser,
    session: Database,
    gateway: Gateway,
) -> HintRead:
    hint = await HintService(session, gateway=gateway).get_hint(
        current_user, question_id, data
    )
    return HintRead.model_validate(hint)
