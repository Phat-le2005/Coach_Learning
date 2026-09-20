from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.ai.schemas import AIRequestLogPagination, AIUsageSummaryRead
from app.ai.usage_service import AIUsageService
from app.auth.dependencies import require_role
from app.database.session import get_db
from app.users.models import Role, User

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])


@router.get(
    "/usage",
    response_model=AIRequestLogPagination,
    dependencies=[Depends(require_role(Role.ADMIN))],
)
def get_ai_usage_logs(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    task: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AIRequestLogPagination:
    """Retrieve paginated AI request execution logs for auditing and observability."""
    response.headers["Cache-Control"] = "no-store"
    service = AIUsageService(session)
    return service.get_logs(
        start_date=start_date,
        end_date=end_date,
        task=task,
        provider=provider,
        model=model,
        success=success,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/usage/summary",
    response_model=AIUsageSummaryRead,
    dependencies=[Depends(require_role(Role.ADMIN))],
)
def get_ai_usage_summary(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    task: str | None = Query(default=None),
    provider: str | None = Query(default=None),
) -> AIUsageSummaryRead:
    """Retrieve aggregated AI usage summary metrics:
    
    - requests/day
    - requests/task
    - tokens/task
    - average latency
    - failure rate
    - estimated cost
    """
    response.headers["Cache-Control"] = "no-store"
    service = AIUsageService(session)
    return service.get_usage_summary(
        start_date=start_date,
        end_date=end_date,
        task=task,
        provider=provider,
    )
