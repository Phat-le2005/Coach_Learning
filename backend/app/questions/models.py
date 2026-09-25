from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, event, func, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.questions.fingerprint import question_content_hash

if TYPE_CHECKING:
    from app.hints.models import QuestionHint


class QuestionType(StrEnum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"
    OPEN_RESPONSE = "OPEN_RESPONSE"


class QuestionStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class CognitiveLevel(StrEnum):
    REMEMBER = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY = "APPLY"
    ANALYZE = "ANALYZE"


class QuestionGroupType(StrEnum):
    TRUE_FALSE_FOUR = "TRUE_FALSE_FOUR"


class QuestionGroupScoringPolicy(StrEnum):
    MOET_2025_TRUE_FALSE = "MOET_2025_TRUE_FALSE"


class ImportFileFormat(StrEnum):
    CSV = "CSV"
    JSON = "JSON"


class ImportBatchStatus(StrEnum):
    PREVIEWED = "PREVIEWED"
    IMPORTED = "IMPORTED"


class ImportRowStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    DUPLICATE = "DUPLICATE"
    IMPORTED = "IMPORTED"


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("length(trim(content)) > 0", name="content_not_blank"),
        CheckConstraint("length(content_hash) = 64", name="content_hash_length"),
        CheckConstraint("difficulty BETWEEN 0.0 AND 1.0", name="difficulty_range"),
        CheckConstraint("length(trim(source_type)) > 0", name="source_type_not_blank"),
        CheckConstraint("exam_weight BETWEEN 0.0 AND 1.0", name="exam_weight_range"),
        CheckConstraint("correct_answer IS NULL OR length(trim(correct_answer)) > 0", name="correct_answer_not_blank"),
        CheckConstraint("explanation IS NULL OR length(trim(explanation)) > 0", name="explanation_not_blank"),
        CheckConstraint("source_reference IS NULL OR length(trim(source_reference)) > 0", name="source_reference_not_blank"),
        CheckConstraint("source_year IS NULL OR source_year BETWEEN 1900 AND 2100", name="source_year_range"),
        Index("ix_questions_subject_status_type_difficulty", "subject_id", "status", "question_type", "difficulty"),
        Index("ix_questions_content_hash", "content_hash"),
        Index("ix_questions_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(Enum(QuestionType, native_enum=False, create_constraint=True, name="question_type"), nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cognitive_level: Mapped[CognitiveLevel | None] = mapped_column(
        Enum(
            CognitiveLevel,
            native_enum=False,
            create_constraint=True,
            name="question_cognitive_level",
        ),
        nullable=True,
    )
    exam_weight: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[QuestionStatus] = mapped_column(Enum(QuestionStatus, native_enum=False, create_constraint=True, name="question_status"), nullable=False, default=QuestionStatus.DRAFT, server_default=QuestionStatus.DRAFT.value)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    options: Mapped[list["QuestionOption"]] = relationship(back_populates="question", cascade="all, delete-orphan", passive_deletes=True, order_by="QuestionOption.order_index")
    concept_links: Mapped[list["QuestionConcept"]] = relationship(back_populates="question", cascade="all, delete-orphan", passive_deletes=True)
    problem_type_links: Mapped[list["QuestionProblemType"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", passive_deletes=True
    )
    learning_outcome_links: Mapped[list["QuestionLearningOutcome"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", passive_deletes=True
    )
    hints: Mapped[list["QuestionHint"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionHint.hint_level",
    )


@event.listens_for(Question, "before_insert")
@event.listens_for(Question, "before_update")
def _synchronize_question_content_hash(
    mapper: object, connection: object, target: Question
) -> None:
    target.content_hash = question_content_hash(target.content)


class QuestionGroup(Base):
    __tablename__ = "question_groups"
    __table_args__ = (
        CheckConstraint("length(trim(content)) > 0", name="content_not_blank"),
        CheckConstraint("difficulty BETWEEN 0.0 AND 1.0", name="difficulty_range"),
        CheckConstraint(
            "length(trim(source_type)) > 0", name="source_type_not_blank"
        ),
        CheckConstraint(
            "source_reference IS NULL OR length(trim(source_reference)) > 0",
            name="source_reference_not_blank",
        ),
        CheckConstraint(
            "source_year IS NULL OR source_year BETWEEN 1900 AND 2100",
            name="source_year_range",
        ),
        CheckConstraint("exam_weight BETWEEN 0.0 AND 1.0", name="exam_weight_range"),
        Index(
            "ix_question_groups_subject_status_type_difficulty",
            "subject_id",
            "status",
            "group_type",
            "difficulty",
        ),
        Index("ix_question_groups_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    group_type: Mapped[QuestionGroupType] = mapped_column(
        Enum(
            QuestionGroupType,
            native_enum=False,
            create_constraint=True,
            name="question_group_type",
        ),
        nullable=False,
    )
    scoring_policy: Mapped[QuestionGroupScoringPolicy] = mapped_column(
        Enum(
            QuestionGroupScoringPolicy,
            native_enum=False,
            create_constraint=True,
            name="question_group_scoring_policy",
        ),
        nullable=False,
    )
    difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cognitive_level: Mapped[CognitiveLevel | None] = mapped_column(
        Enum(
            CognitiveLevel,
            native_enum=False,
            create_constraint=True,
            name="question_group_cognitive_level",
        ),
        nullable=True,
    )
    exam_weight: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(
            QuestionStatus,
            native_enum=False,
            create_constraint=True,
            name="question_group_status",
        ),
        nullable=False,
        default=QuestionStatus.DRAFT,
        server_default=QuestionStatus.DRAFT.value,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["QuestionGroupItem"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionGroupItem.order_index",
    )


class QuestionGroupItem(Base):
    __tablename__ = "question_group_items"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "label", name="uq_question_group_items_group_label"
        ),
        UniqueConstraint(
            "group_id", "order_index", name="uq_question_group_items_group_order"
        ),
        UniqueConstraint("question_id", name="uq_question_group_items_question"),
        CheckConstraint("label IN ('a', 'b', 'c', 'd')", name="label_allowed"),
        CheckConstraint(
            "order_index BETWEEN 0 AND 3", name="order_index_range"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_groups.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(1), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    group: Mapped[QuestionGroup] = relationship(back_populates="items")
    question: Mapped[Question] = relationship()


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "label", name="uq_question_options_question_label"),
        UniqueConstraint("question_id", "order_index", name="uq_question_options_question_order"),
        CheckConstraint("length(trim(label)) > 0", name="label_not_blank"),
        CheckConstraint("length(trim(content)) > 0", name="content_not_blank"),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[Question] = relationship(back_populates="options")


class QuestionConcept(Base):
    __tablename__ = "question_concepts"
    __table_args__ = (
        CheckConstraint("weight > 0.0 AND weight <= 1.0", name="weight_range"),
        Index("ix_question_concepts_concept_question", "concept_id", "question_id"),
    )
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    concept_id: Mapped[UUID] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    question: Mapped[Question] = relationship(back_populates="concept_links")


class QuestionProblemType(Base):
    __tablename__ = "question_problem_types"
    __table_args__ = (
        CheckConstraint(
            "weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name="weight_range"
        ),
        Index(
            "ix_question_problem_types_problem_type_question",
            "problem_type_id",
            "question_id",
        ),
    )

    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), primary_key=True
    )
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    question: Mapped[Question] = relationship(back_populates="problem_type_links")


class QuestionLearningOutcome(Base):
    __tablename__ = "question_learning_outcomes"
    __table_args__ = (
        CheckConstraint(
            "weight IS NULL OR (weight > 0.0 AND weight <= 1.0)", name="weight_range"
        ),
        Index(
            "ix_question_learning_outcomes_outcome_question",
            "learning_outcome_id",
            "question_id",
        ),
    )

    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    learning_outcome_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), primary_key=True
    )
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    question: Mapped[Question] = relationship(back_populates="learning_outcome_links")


class QuestionImportBatch(Base):
    __tablename__ = "question_import_batches"
    __table_args__ = (
        CheckConstraint("length(trim(file_name)) > 0", name="file_name_not_blank"),
        Index("ix_question_import_batches_created_by_status", "created_by", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[ImportFileFormat] = mapped_column(
        Enum(
            ImportFileFormat,
            native_enum=False,
            create_constraint=True,
            name="question_import_file_format",
        ),
        nullable=False,
    )
    trusted_seed_data: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    status: Mapped[ImportBatchStatus] = mapped_column(
        Enum(
            ImportBatchStatus,
            native_enum=False,
            create_constraint=True,
            name="question_import_batch_status",
        ),
        nullable=False,
        default=ImportBatchStatus.PREVIEWED,
        server_default=ImportBatchStatus.PREVIEWED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rows: Mapped[list["QuestionImportRow"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionImportRow.row_number",
    )


class QuestionImportRow(Base):
    __tablename__ = "question_import_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_question_import_rows_batch_row"),
        CheckConstraint("row_number > 0", name="row_number_positive"),
        CheckConstraint(
            "content_hash IS NULL OR length(content_hash) = 64",
            name="content_hash_length",
        ),
        Index("ix_question_import_rows_batch_status", "batch_id", "status", "row_number"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ImportRowStatus] = mapped_column(
        Enum(
            ImportRowStatus,
            native_enum=False,
            create_constraint=True,
            name="question_import_row_status",
        ),
        nullable=False,
    )
    raw_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    normalized_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    imported_question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )

    batch: Mapped[QuestionImportBatch] = relationship(back_populates="rows")
