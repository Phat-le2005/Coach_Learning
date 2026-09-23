from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class AdmissionTargetType(StrEnum):
    """Student target category.

    Strict Pedagogical / Architectural Guarantee:
    - Target type is ONLY a personal preference / categorization chosen by the student.
    - The system NEVER automatically assesses, assumes, or decides whether an institution is 'SAFE'
      unless governed by independent, verified deterministic score logic.
    """
    DREAM = "DREAM"
    TARGET = "TARGET"
    SAFE = "SAFE"


class AdmissionImportFormat(StrEnum):
    CSV = "CSV"
    JSON = "JSON"
    DIRECT_FEED = "DIRECT_FEED"


class AdmissionImportStatus(StrEnum):
    PREVIEWED = "PREVIEWED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class University(Base):
    __tablename__ = "universities"
    __table_args__ = (
        CheckConstraint("length(trim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_universities_code", "code", unique=True),
        Index("ix_universities_region", "region"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    majors: Mapped[list["Major"]] = relationship(
        back_populates="university", cascade="all, delete-orphan", passive_deletes=True
    )
    admission_rules: Mapped[list["AdmissionRule"]] = relationship(
        back_populates="university", cascade="all, delete-orphan", passive_deletes=True
    )
    admission_targets: Mapped[list["AdmissionTarget"]] = relationship(
        back_populates="university", cascade="all, delete-orphan", passive_deletes=True
    )


class Major(Base):
    __tablename__ = "majors"
    __table_args__ = (
        UniqueConstraint("university_id", "code", name="uq_majors_university_code"),
        CheckConstraint("length(trim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_majors_university_code", "university_id", "code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    university: Mapped["University"] = relationship(back_populates="majors")
    admission_rules: Mapped[list["AdmissionRule"]] = relationship(
        back_populates="major", cascade="all, delete-orphan", passive_deletes=True
    )
    admission_targets: Mapped[list["AdmissionTarget"]] = relationship(
        back_populates="major", cascade="all, delete-orphan", passive_deletes=True
    )


class AdmissionMethod(Base):
    __tablename__ = "admission_methods"
    __table_args__ = (
        CheckConstraint("length(trim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_admission_methods_code", "code", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rules: Mapped[list["AdmissionRule"]] = relationship(back_populates="method")


class AdmissionDataSource(Base):
    __tablename__ = "admission_data_sources"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("published_year >= 2000", name="published_year_valid"),
        Index("ix_admission_data_sources_year", "published_year"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, default="OFFICIAL_PORTAL")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(300), nullable=True)
    published_year: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rules: Mapped[list["AdmissionRule"]] = relationship(back_populates="data_source")


class AdmissionImportHistory(Base):
    """Audit and provenance log for admission data import batches."""

    __tablename__ = "admission_import_histories"
    __table_args__ = (
        CheckConstraint("length(trim(file_name)) > 0", name="file_name_not_blank"),
        Index("ix_admission_import_histories_status", "status"),
        Index("ix_admission_import_histories_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[AdmissionImportFormat] = mapped_column(
        Enum(
            AdmissionImportFormat,
            native_enum=False,
            create_constraint=True,
            name="admission_import_format",
        ),
        nullable=False,
    )
    status: Mapped[AdmissionImportStatus] = mapped_column(
        Enum(
            AdmissionImportStatus,
            native_enum=False,
            create_constraint=True,
            name="admission_import_status",
        ),
        nullable=False,
        default=AdmissionImportStatus.PREVIEWED,
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    preview_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    target_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admission_data_sources.id", ondelete="SET NULL"), nullable=True
    )
    data_source_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    data_source: Mapped["AdmissionDataSource | None"] = relationship()
    rules: Mapped[list["AdmissionRule"]] = relationship(back_populates="import_history")


class AdmissionRule(Base):
    """Admission rules versioned strictly by year.

    Guarantees:
    - Regulations and criteria are fully parameterized in database, NEVER hardcoded in Python code.
    - Verified against official sources; LLMs are NOT the source of truth.
    """
    __tablename__ = "admission_rules"
    __table_args__ = (
        UniqueConstraint(
            "major_id", "year", "method_id", "subject_combination",
            name="uq_admission_rules_major_year_method_combination",
        ),
        CheckConstraint("year >= 2000", name="year_valid"),
        CheckConstraint("quota IS NULL OR quota >= 0", name="quota_nonnegative"),
        CheckConstraint("historical_score IS NULL OR historical_score >= 0.0", name="historical_score_nonnegative"),
        Index("ix_admission_rules_university_year", "university_id", "year"),
        Index("ix_admission_rules_major_year", "major_id", "year"),
        Index("ix_admission_rules_year_method", "year", "method_id"),
        Index("ix_admission_rules_import_history", "import_history_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    university_id: Mapped[UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), nullable=False
    )
    major_id: Mapped[UUID] = mapped_column(
        ForeignKey("majors.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    method_id: Mapped[UUID] = mapped_column(
        ForeignKey("admission_methods.id", ondelete="RESTRICT"), nullable=False
    )
    subject_combination: Mapped[str] = mapped_column(String(100), nullable=False)
    requirements: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    historical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admission_data_sources.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    import_history_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admission_import_histories.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    university: Mapped["University"] = relationship(back_populates="admission_rules")
    major: Mapped["Major"] = relationship(back_populates="admission_rules")
    method: Mapped["AdmissionMethod"] = relationship(back_populates="rules")
    data_source: Mapped["AdmissionDataSource | None"] = relationship(back_populates="rules")
    import_history: Mapped["AdmissionImportHistory | None"] = relationship(back_populates="rules")


class AdmissionTarget(Base):
    """Student admission targets (aspirations).

    Category types:
    - DREAM: Trường / ngành mơ ước, thách thức cao.
    - TARGET: Trường / ngành mục tiêu chính.
    - SAFE: Trường / ngành an toàn dự phòng.
    """
    __tablename__ = "student_admission_targets"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "university_id", "major_id", "target_year",
            name="uq_student_admission_targets_student_major_year",
        ),
        CheckConstraint("priority_order >= 1", name="priority_order_positive"),
        CheckConstraint("target_year >= 2020", name="target_year_valid"),
        Index("ix_student_admission_targets_student_year", "student_id", "target_year"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False
    )
    university_id: Mapped[UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), nullable=False
    )
    major_id: Mapped[UUID] = mapped_column(
        ForeignKey("majors.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[AdmissionTargetType] = mapped_column(
        Enum(
            AdmissionTargetType,
            native_enum=False,
            create_constraint=True,
            name="admission_target_type",
        ),
        nullable=False,
    )
    target_year: Mapped[int] = mapped_column(Integer, nullable=False, default=2026)
    priority_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    university: Mapped["University"] = relationship(back_populates="admission_targets")
    major: Mapped["Major"] = relationship(back_populates="admission_targets")
