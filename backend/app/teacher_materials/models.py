from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.questions.models import QuestionType


class TeacherMaterialStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSED = "PARSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MAPPING_PENDING = "MAPPING_PENDING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class MaterialItemExtractionStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class MaterialEvaluationMode(StrEnum):
    OBJECTIVE_AUTO = "OBJECTIVE_AUTO"
    OPEN_RESPONSE = "OPEN_RESPONSE"
    TEACHER_REVIEW = "TEACHER_REVIEW"


class MaterialMappingSource(StrEnum):
    AI = "AI"
    TEACHER = "TEACHER"
    DETERMINISTIC = "DETERMINISTIC"


class MaterialMappingStatus(StrEnum):
    SUGGESTED = "SUGGESTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class TeacherMaterial(Base):
    __tablename__ = "teacher_materials"
    __table_args__ = (
        UniqueConstraint("classroom_id", "sha256", name="uq_teacher_materials_classroom_sha256"),
        CheckConstraint("length(sha256) = 64", name="sha256_length"),
        CheckConstraint("file_size_bytes > 0", name="file_size_positive"),
        CheckConstraint("page_count IS NULL OR page_count > 0", name="page_count_positive"),
        Index("ix_teacher_materials_classroom_status", "classroom_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    classroom_id: Mapped[UUID] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    teaching_plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("teaching_plans.id", ondelete="SET NULL"))
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[TeacherMaterialStatus] = mapped_column(Enum(TeacherMaterialStatus, native_enum=False, name="teacher_material_status"), default=TeacherMaterialStatus.UPLOADED, server_default=TeacherMaterialStatus.UPLOADED.value, nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    items: Mapped[list["TeacherMaterialItem"]] = relationship(back_populates="material", cascade="all, delete-orphan", passive_deletes=True, order_by="TeacherMaterialItem.order_index")


class TeacherMaterialItem(Base):
    __tablename__ = "teacher_material_items"
    __table_args__ = (
        UniqueConstraint("teacher_material_id", "order_index", name="uq_teacher_material_items_material_order"),
        CheckConstraint("order_index >= 0", name="order_nonnegative"),
        CheckConstraint("length(content_hash) = 64", name="content_hash_length"),
        CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 0 AND 1", name="difficulty_range"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    teacher_material_id: Mapped[UUID] = mapped_column(ForeignKey("teacher_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    question_type: Mapped[QuestionType | None] = mapped_column(Enum(QuestionType, native_enum=False, name="material_question_type"))
    correct_answer: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[float | None] = mapped_column(Float)
    extraction_status: Mapped[MaterialItemExtractionStatus] = mapped_column(Enum(MaterialItemExtractionStatus, native_enum=False, name="material_item_extraction_status"), nullable=False)
    evaluation_mode: Mapped[MaterialEvaluationMode] = mapped_column(Enum(MaterialEvaluationMode, native_enum=False, name="material_evaluation_mode"), nullable=False)
    raw_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    material: Mapped[TeacherMaterial] = relationship(back_populates="items")
    options: Mapped[list["TeacherMaterialItemOption"]] = relationship(back_populates="item", cascade="all, delete-orphan", passive_deletes=True, order_by="TeacherMaterialItemOption.order_index")
    problem_type_mappings: Mapped[list["TeacherMaterialItemProblemType"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    concept_mappings: Mapped[list["TeacherMaterialItemConcept"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    learning_outcome_mappings: Mapped[list["TeacherMaterialItemLearningOutcome"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class TeacherMaterialItemOption(Base):
    __tablename__ = "teacher_material_item_options"
    __table_args__ = (UniqueConstraint("item_id", "label", name="uq_material_options_item_label"), UniqueConstraint("item_id", "order_index", name="uq_material_options_item_order"))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("teacher_material_items.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    item: Mapped[TeacherMaterialItem] = relationship(back_populates="options")


class _MappingMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("teacher_material_items.id", ondelete="CASCADE"), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[MaterialMappingSource] = mapped_column(Enum(MaterialMappingSource, native_enum=False, name="material_mapping_source"), nullable=False)
    status: Mapped[MaterialMappingStatus] = mapped_column(Enum(MaterialMappingStatus, native_enum=False, name="material_mapping_status"), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TeacherMaterialItemProblemType(_MappingMixin, Base):
    __tablename__ = "teacher_material_item_problem_types"
    __table_args__ = (UniqueConstraint("item_id", "problem_type_id", name="uq_material_item_problem_type"), CheckConstraint("weight > 0 AND weight <= 1 AND confidence BETWEEN 0 AND 1", name="mapping_ranges"))
    problem_type_id: Mapped[UUID] = mapped_column(ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=False)


class TeacherMaterialItemConcept(_MappingMixin, Base):
    __tablename__ = "teacher_material_item_concepts"
    __table_args__ = (UniqueConstraint("item_id", "concept_id", name="uq_material_item_concept"), CheckConstraint("weight > 0 AND weight <= 1 AND confidence BETWEEN 0 AND 1", name="mapping_ranges"))
    concept_id: Mapped[UUID] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False)


class TeacherMaterialItemLearningOutcome(_MappingMixin, Base):
    __tablename__ = "teacher_material_item_learning_outcomes"
    __table_args__ = (UniqueConstraint("item_id", "learning_outcome_id", name="uq_material_item_learning_outcome"), CheckConstraint("weight > 0 AND weight <= 1 AND confidence BETWEEN 0 AND 1", name="mapping_ranges"))
    learning_outcome_id: Mapped[UUID] = mapped_column(ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), nullable=False)
