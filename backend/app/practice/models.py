from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.questions.models import QuestionGroupScoringPolicy


class PracticeSessionType(StrEnum):
    DIAGNOSTIC = "DIAGNOSTIC"
    PRACTICE = "PRACTICE"
    REVIEW = "REVIEW"
    REPAIR = "REPAIR"
    QUICK_CHECK = "QUICK_CHECK"
    EXAM = "EXAM"


class PracticeSessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class EvaluationStatus(StrEnum):
    AUTO_EVALUATED = "AUTO_EVALUATED"
    NEEDS_EVALUATION = "NEEDS_EVALUATION"
    EVALUATED = "EVALUATED"
    NEEDS_TEACHER_REVIEW = "NEEDS_TEACHER_REVIEW"


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        UniqueConstraint("id", "student_id", name="uq_practice_sessions_id_student_id"),
        CheckConstraint(
            "(status = 'ACTIVE' AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'ABANDONED') AND completed_at IS NOT NULL)",
            name="status_completed_at_consistency",
        ),
        Index("ix_practice_sessions_student_status_started", "student_id", "status", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    session_type: Mapped[PracticeSessionType] = mapped_column(
        Enum(
            PracticeSessionType,
            native_enum=False,
            create_constraint=True,
            name="practice_session_type",
        ),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[PracticeSessionStatus] = mapped_column(
        Enum(
            PracticeSessionStatus,
            native_enum=False,
            create_constraint=True,
            name="practice_session_status",
        ),
        nullable=False,
        default=PracticeSessionStatus.ACTIVE,
        server_default=PracticeSessionStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    problem_type_links: Mapped[list["PracticeSessionProblemType"]] = relationship(
        back_populates="practice_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PracticeSessionProblemType.problem_type_id",
    )
    concept_links: Mapped[list["PracticeSessionConcept"]] = relationship(
        back_populates="practice_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PracticeSessionConcept.concept_id",
    )
    attempts: Mapped[list["QuestionAttempt"]] = relationship(
        back_populates="practice_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionAttempt.attempt_number",
    )
    group_attempts: Mapped[list["QuestionGroupAttempt"]] = relationship(
        back_populates="practice_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionGroupAttempt.created_at",
    )


class PracticeSessionProblemType(Base):
    __tablename__ = "practice_session_problem_types"

    practice_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), primary_key=True
    )

    practice_session: Mapped[PracticeSession] = relationship(back_populates="problem_type_links")


class PracticeSessionConcept(Base):
    __tablename__ = "practice_session_concepts"

    practice_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), primary_key=True
    )

    practice_session: Mapped[PracticeSession] = relationship(back_populates="concept_links")


class QuestionAttempt(Base):
    __tablename__ = "question_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["practice_session_id", "student_id"],
            ["practice_sessions.id", "practice_sessions.student_id"],
            ondelete="CASCADE",
            name="fk_question_attempts_session_student_practice_sessions",
        ),
        UniqueConstraint(
            "practice_session_id",
            "question_id",
            name="uq_question_attempts_session_question",
        ),
        UniqueConstraint(
            "practice_session_id",
            "attempt_number",
            name="uq_question_attempts_session_attempt_number",
        ),
        CheckConstraint("length(trim(student_answer)) > 0", name="student_answer_not_blank"),
        CheckConstraint("score IS NULL OR score BETWEEN 0.0 AND 1.0", name="score_range"),
        CheckConstraint(
            "response_time_seconds IS NULL OR response_time_seconds > 0",
            name="response_time_positive",
        ),
        CheckConstraint("hint_count >= 0", name="hint_count_nonnegative"),
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        Index("ix_question_attempts_student_created", "student_id", "created_at"),
        Index("ix_question_attempts_question_created", "question_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    practice_session_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    student_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    student_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluation_status: Mapped[EvaluationStatus] = mapped_column(
        Enum(
            EvaluationStatus,
            native_enum=False,
            create_constraint=True,
            name="question_attempt_evaluation_status",
        ),
        nullable=False,
    )
    evaluation_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    practice_session: Mapped[PracticeSession] = relationship(back_populates="attempts")
    group_attempt_item: Mapped["QuestionGroupAttemptItem | None"] = relationship(
        back_populates="question_attempt",
        uselist=False,
    )


class QuestionGroupAttempt(Base):
    __tablename__ = "question_group_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["practice_session_id", "student_id"],
            ["practice_sessions.id", "practice_sessions.student_id"],
            ondelete="CASCADE",
            name="fk_group_attempts_session_student_practice_sessions",
        ),
        UniqueConstraint(
            "practice_session_id",
            "question_group_id",
            name="uq_question_group_attempts_session_group",
        ),
        CheckConstraint(
            "correct_count BETWEEN 0 AND 4", name="correct_count_range"
        ),
        CheckConstraint("score BETWEEN 0.0 AND 1.0", name="score_range"),
        CheckConstraint(
            "response_time_seconds IS NULL OR response_time_seconds > 0",
            name="response_time_positive",
        ),
        Index(
            "ix_question_group_attempts_student_created", "student_id", "created_at"
        ),
        Index(
            "ix_question_group_attempts_group_created",
            "question_group_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    practice_session_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    student_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    question_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_groups.id", ondelete="RESTRICT"), nullable=False
    )
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    response_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    scoring_policy: Mapped[QuestionGroupScoringPolicy] = mapped_column(
        Enum(
            QuestionGroupScoringPolicy,
            native_enum=False,
            create_constraint=True,
            name="question_group_attempt_scoring_policy",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    practice_session: Mapped[PracticeSession] = relationship(
        back_populates="group_attempts"
    )
    question_group: Mapped["QuestionGroup"] = relationship()
    attempt_items: Mapped[list["QuestionGroupAttemptItem"]] = relationship(
        back_populates="group_attempt",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionGroupAttemptItem.order_index",
    )


class QuestionGroupAttemptItem(Base):
    __tablename__ = "question_group_attempt_items"
    __table_args__ = (
        UniqueConstraint(
            "question_group_attempt_id",
            "label",
            name="uq_question_group_attempt_items_parent_label",
        ),
        UniqueConstraint(
            "question_group_attempt_id",
            "order_index",
            name="uq_question_group_attempt_items_parent_order",
        ),
        UniqueConstraint(
            "question_attempt_id",
            name="uq_question_group_attempt_items_question_attempt",
        ),
        CheckConstraint("label IN ('a', 'b', 'c', 'd')", name="label_allowed"),
        CheckConstraint(
            "order_index BETWEEN 0 AND 3", name="order_index_range"
        ),
        Index(
            "ix_question_group_attempt_items_group_item", "question_group_item_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    question_group_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_group_attempts.id", ondelete="CASCADE"), nullable=False
    )
    question_group_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_group_items.id", ondelete="RESTRICT"), nullable=False
    )
    question_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_attempts.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(1), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    group_attempt: Mapped[QuestionGroupAttempt] = relationship(
        back_populates="attempt_items"
    )
    question_group_item: Mapped["QuestionGroupItem"] = relationship()
    question_attempt: Mapped[QuestionAttempt] = relationship(
        back_populates="group_attempt_item"
    )
