from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class MathCanvasExplanation(Base):
    __tablename__ = "math_canvas_explanations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("math_solution_attempts.id", ondelete="CASCADE"), index=True)
    spec_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MathCanvasSnapshot(Base):
    __tablename__ = "math_canvas_snapshots"
    __table_args__ = (
        UniqueConstraint("attempt_id", "client_action_id", name="uq_math_canvas_action"),
        Index("ix_math_canvas_student_created", "student_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("math_solution_attempts.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="RESTRICT"))
    client_action_id: Mapped[UUID] = mapped_column(Uuid)
    request_hash: Mapped[str] = mapped_column(String(64))
    expression: Mapped[str] = mapped_column(String(500))
    dimension: Mapped[str] = mapped_column(String(2))
    settings: Mapped[dict] = mapped_column(JSON)
    camera: Mapped[dict] = mapped_column(JSON)
    page_index: Mapped[int] = mapped_column(Integer)
    source_latex: Mapped[str] = mapped_column(String(500))
    source_strokes: Mapped[list] = mapped_column(JSON)
    source_ink_revision: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text)
    explanation_id: Mapped[UUID | None] = mapped_column(ForeignKey("math_canvas_explanations.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
