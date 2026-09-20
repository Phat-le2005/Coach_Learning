from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class AIRequestLog(Base):
    """AI request telemetry and usage audit log.
    
    Privacy guarantee: Raw sensitive prompts and raw completion texts are NEVER stored.
    Only technical metadata (task, model, prompt name/version, latency, token count, cost)
    is recorded for observability and analytics.
    """

    __tablename__ = "ai_request_logs"
    __table_args__ = (
        Index("ix_ai_request_logs_provider_model", "provider", "model"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        server_default="default",
    )
    prompt_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="v1",
        server_default="v1",
    )
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
        index=True,
    )
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id])
