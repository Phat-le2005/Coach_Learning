from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.curriculum.constants import LEGACY_CURRICULUM_VERSION_ID
from app.database.base import Base


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("curriculum_version_id", "code", name="uq_subjects_version_code"),
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("grade_level BETWEEN 1 AND 12", name="grade_level_range"),
        CheckConstraint("description IS NULL OR length(trim(description)) > 0", name="description_not_blank"),
        CheckConstraint("order_index IS NULL OR order_index >= 0", name="order_index_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    curriculum_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="RESTRICT"),
        nullable=False,
        default=LEGACY_CURRICULUM_VERSION_ID,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    grade_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
