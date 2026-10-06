import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Application liveness; intentionally independent of PostgreSQL and AI."""
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
def ready(db: Session = Depends(get_db)) -> ReadyResponse:
    """Application readiness; verifies database connectivity."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Readiness check failed (%s)", type(exc).__name__)
        raise ApplicationError(
            status_code=503,
            code="SERVICE_NOT_READY",
            message="Database dependency is unavailable.",
        ) from None
    return ReadyResponse()
