from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
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
    Text,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.concepts.models import Concept
    from app.curriculum.models import ProblemType
    from app.questions.models import Question
    from app.students.models import StudentProfile
    from app.subjects.models import Subject


class LearningMemoryType(StrEnum):
    """Types of long-term learning memory captured for a student."""

    LEARNING_PREFERENCE = "LEARNING_PREFERENCE"
    PERSISTENT_DIFFICULTY = "PERSISTENT_DIFFICULTY"
    PERSISTENT_MISCONCEPTION = "PERSISTENT_MISCONCEPTION"
    IMPORTANT_ACADEMIC_GOAL = "IMPORTANT_ACADEMIC_GOAL"
    TUTORING_PREFERENCE = "TUTORING_PREFERENCE"


class TutorSessionStatus(StrEnum):
    """Lifecycle status of an AI tutoring session."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class TutorSession(Base):
    """Represents a bounded interaction session between a student and the AI Tutor.
    
    Privacy boundary: Raw transcripts are transient and NOT stored as long-term memory.
    """

    __tablename__ = "tutor_sessions"
    __table_args__ = (
        CheckConstraint("turn_count >= 0", name="tutor_sessions_turn_count_nonnegative"),
        Index("ix_tutor_sessions_student_status", "student_id", "status"),
        Index("ix_tutor_sessions_student_started", "student_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="SET NULL"), nullable=True
    )
    concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True
    )
    question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[TutorSessionStatus] = mapped_column(
        Enum(
            TutorSessionStatus,
            native_enum=False,
            create_constraint=True,
            name="tutor_session_status",
        ),
        nullable=False,
        default=TutorSessionStatus.ACTIVE,
        server_default=TutorSessionStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    student: Mapped[StudentProfile] = relationship()
    subject: Mapped[Subject | None] = relationship()
    problem_type: Mapped[ProblemType | None] = relationship()
    concept: Mapped[Concept | None] = relationship()
    question: Mapped[Question | None] = relationship()
    summary: Mapped[TutorSessionSummary | None] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    memories: Mapped[list[StudentLearningMemory]] = relationship(back_populates="source_session")


class TutorSessionSummary(Base):
    """Academic summary of a completed tutoring session.
    
    Synthesizes academic insights without preserving full raw conversational chat logs.
    """

    __tablename__ = "tutor_session_summaries"
    __table_args__ = (
        Index("ix_tutor_session_summaries_student_id", "student_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("tutor_sessions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_takeaways: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    resolved_questions_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[TutorSession] = relationship(back_populates="summary")
    student: Mapped[StudentProfile] = relationship()


class StudentLearningMemory(Base):
    """Persistent structured learning memory of a student.
    
    Strict Guardrails:
    - Never stores casual talk, temporary emotions, sensitive personal data, or raw chats.
    - Captures verified learning preferences, persistent difficulties/misconceptions, and academic goals.
    """

    __tablename__ = "student_learning_memories"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="learning_memory_confidence_range"),
        Index("ix_student_learning_memories_student_type", "student_id", "type"),
        Index("ix_student_learning_memories_student_concept", "student_id", "concept_id"),
        Index("ix_student_learning_memories_student_pt", "student_id", "problem_type_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[LearningMemoryType] = mapped_column(
        Enum(
            LearningMemoryType,
            native_enum=False,
            create_constraint=True,
            name="learning_memory_type",
        ),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="SET NULL"), nullable=True
    )
    concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True
    )
    source_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tutor_sessions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    student: Mapped[StudentProfile] = relationship()
    problem_type: Mapped[ProblemType | None] = relationship()
    concept: Mapped[Concept | None] = relationship()
    source_session: Mapped[TutorSession | None] = relationship(back_populates="memories")
