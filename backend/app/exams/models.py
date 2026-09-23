from datetime import datetime
from enum import StrEnum
from typing import Any, TYPE_CHECKING
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.questions.models import Question
    from app.students.models import StudentProfile
    from app.subjects.models import Subject
    from app.users.models import User


class ExamStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ExamType(StrEnum):
    REAL_SIMULATION = "REAL_SIMULATION"
    MOCK_PRACTICE = "MOCK_PRACTICE"
    DIAGNOSTIC_EXAM = "DIAGNOSTIC_EXAM"


class ExamAttemptStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"
    TIMED_OUT = "TIMED_OUT"
    ABANDONED = "ABANDONED"


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
        CheckConstraint("total_points > 0", name="total_points_positive"),
        Index("ix_exams_subject_status", "subject_id", "status"),
        Index("ix_exams_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    status: Mapped[ExamStatus] = mapped_column(
        Enum(
            ExamStatus,
            native_enum=False,
            create_constraint=True,
            name="exam_status",
        ),
        nullable=False,
        default=ExamStatus.DRAFT,
        server_default=ExamStatus.DRAFT.value,
    )
    exam_type: Mapped[ExamType] = mapped_column(
        Enum(
            ExamType,
            native_enum=False,
            create_constraint=True,
            name="exam_type",
        ),
        nullable=False,
        default=ExamType.REAL_SIMULATION,
        server_default=ExamType.REAL_SIMULATION.value,
    )
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_points: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    passing_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    blueprint_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    subject: Mapped["Subject"] = relationship()
    creator: Mapped["User"] = relationship()
    sections: Mapped[list["ExamSection"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", order_by="ExamSection.order_index"
    )
    questions: Mapped[list["ExamQuestion"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", order_by="ExamQuestion.order_index"
    )
    attempts: Mapped[list["ExamAttempt"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan"
    )


class ExamSection(Base):
    __tablename__ = "exam_sections"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
        Index("ix_exam_sections_exam_order", "exam_id", "order_index"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    exam_id: Mapped[UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    blueprint_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    exam: Mapped[Exam] = relationship(back_populates="sections")
    questions: Mapped[list["ExamQuestion"]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="ExamQuestion.order_index"
    )


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (
        UniqueConstraint("exam_id", "question_id", name="uq_exam_questions_exam_question"),
        UniqueConstraint("exam_id", "order_index", name="uq_exam_questions_exam_order"),
        CheckConstraint("points > 0", name="points_positive"),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
        Index("ix_exam_questions_exam_id", "exam_id"),
        Index("ix_exam_questions_section_id", "section_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    exam_id: Mapped[UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("exam_sections.id", ondelete="CASCADE"), nullable=True
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    exam: Mapped[Exam] = relationship(back_populates="questions")
    section: Mapped[ExamSection | None] = relationship(back_populates="questions")
    question: Mapped["Question"] = relationship()


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        CheckConstraint("duration_seconds >= 0", name="duration_seconds_nonnegative"),
        CheckConstraint("score IS NULL OR score >= 0", name="score_nonnegative"),
        Index("ix_exam_attempts_student_status", "student_id", "status"),
        Index("ix_exam_attempts_exam_student", "exam_id", "student_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    exam_id: Mapped[UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ExamAttemptStatus] = mapped_column(
        Enum(
            ExamAttemptStatus,
            native_enum=False,
            create_constraint=True,
            name="exam_attempt_status",
        ),
        nullable=False,
        default=ExamAttemptStatus.IN_PROGRESS,
        server_default=ExamAttemptStatus.IN_PROGRESS.value,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_points: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    exam: Mapped[Exam] = relationship(back_populates="attempts")
    student: Mapped["StudentProfile"] = relationship()
    responses: Mapped[list["ExamResponse"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan", order_by="ExamResponse.order_answered"
    )


class ExamResponse(Base):
    __tablename__ = "exam_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_exam_responses_attempt_question"),
        CheckConstraint(
            "score_awarded IS NULL OR score_awarded >= 0", name="score_awarded_nonnegative"
        ),
        CheckConstraint(
            "response_time_seconds IS NULL OR response_time_seconds >= 0",
            name="response_time_nonnegative",
        ),
        CheckConstraint("order_answered >= 0", name="order_answered_nonnegative"),
        Index("ix_exam_responses_attempt_id", "attempt_id"),
        Index("ix_exam_responses_question_id", "question_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_option_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score_awarded: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    attempt: Mapped[ExamAttempt] = relationship(back_populates="responses")
    question: Mapped["Question"] = relationship()
