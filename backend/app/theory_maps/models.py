from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.theory_maps.pdf_extraction import unreliable_text_pages


class TheoryMapStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class TheoryDocument(Base):
    __tablename__ = "theory_documents"
    __table_args__ = (
        UniqueConstraint("classroom_id", "sha256", name="uq_theory_classroom_sha"),
        Index("ix_theory_documents_classroom_status", "classroom_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    classroom_id: Mapped[UUID] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_texts: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    nodes: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[TheoryMapStatus] = mapped_column(
        Enum(TheoryMapStatus, native_enum=False, name="theory_map_status"),
        nullable=False, default=TheoryMapStatus.DRAFT,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ai_model: Mapped[str | None] = mapped_column(String(100))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def extraction_warning_pages(self) -> list[int]:
        return unreliable_text_pages(self.page_texts)

    @property
    def source_available(self) -> bool:
        return self.source_published_at is not None
