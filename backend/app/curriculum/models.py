from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Curriculum(Base):
    __tablename__ = "curricula"
    __table_args__ = (
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "description IS NULL OR length(trim(description)) > 0",
            name="description_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CurriculumVersion(Base):
    __tablename__ = "curriculum_versions"
    __table_args__ = (
        UniqueConstraint("curriculum_id", "code", name="uq_curriculum_versions_curriculum_code"),
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(version)) > 0", name="version_not_blank"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="effective_range",
        ),
        CheckConstraint(
            "source_reference IS NULL OR length(trim(source_reference)) > 0",
            name="source_reference_not_blank",
        ),
        Index("ix_curriculum_versions_curriculum_active", "curriculum_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    curriculum_id: Mapped[UUID] = mapped_column(
        ForeignKey("curricula.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("subject_id", "code", name="uq_chapters_subject_code"),
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
        Index("ix_chapters_subject_order", "subject_id", "order_index", "code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("chapter_id", "code", name="uq_topics_chapter_code"),
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
        Index("ix_topics_chapter_order", "chapter_id", "order_index", "code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    chapter_id: Mapped[UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProblemType(Base):
    __tablename__ = "problem_types"
    __table_args__ = (
        UniqueConstraint("topic_id", "code", name="uq_problem_types_topic_code"),
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
        CheckConstraint(
            "default_difficulty IS NULL OR default_difficulty BETWEEN 0.0 AND 1.0",
            name="default_difficulty_range",
        ),
        Index("ix_problem_types_topic_order", "topic_id", "order_index", "code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    default_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LearningOutcome(Base):
    __tablename__ = "learning_outcomes"
    __table_args__ = (
        UniqueConstraint("subject_id", "code", name="uq_learning_outcomes_subject_code"),
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(description)) > 0", name="description_not_blank"),
        CheckConstraint("grade_level BETWEEN 1 AND 12", name="grade_level_range"),
        CheckConstraint("order_index IS NULL OR order_index >= 0", name="order_index_nonnegative"),
        Index("ix_learning_outcomes_subject_order", "subject_id", "order_index", "code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False)
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProblemTypeConcept(Base):
    __tablename__ = "problem_type_concepts"
    __table_args__ = (
        CheckConstraint("weight > 0.0 AND weight <= 1.0", name="weight_range"),
        Index("ix_problem_type_concepts_concept_problem_type", "concept_id", "problem_type_id"),
    )

    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class ProblemTypeLearningOutcome(Base):
    __tablename__ = "problem_type_learning_outcomes"
    __table_args__ = (
        CheckConstraint("weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name="weight_range"),
        Index(
            "ix_problem_type_learning_outcomes_outcome_problem_type",
            "learning_outcome_id",
            "problem_type_id",
        ),
    )

    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="CASCADE"), primary_key=True
    )
    learning_outcome_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), primary_key=True
    )
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)


class CurriculumImportHistory(Base):
    __tablename__ = "curriculum_import_history"
    __table_args__ = (
        UniqueConstraint(
            "dataset_code", "dataset_version", "content_hash",
            name="uq_curriculum_import_history_dataset_version_hash",
        ),
        CheckConstraint("length(content_hash) = 64", name="content_hash_length"),
        Index("ix_curriculum_import_history_version_time", "curriculum_version_id", "imported_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_code: Mapped[str] = mapped_column(String(150), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    curriculum_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="RESTRICT"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
