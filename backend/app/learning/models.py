from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class QuickCheckQuestionRole(StrEnum):
    UNDERSTANDING = "UNDERSTANDING"
    APPLICATION = "APPLICATION"
    PREREQUISITE = "PREREQUISITE"


class QuickCheckVerdict(StrEnum):
    UNDERSTOOD = "UNDERSTOOD"
    PARTIAL = "PARTIAL"
    WEAK = "WEAK"


class ConceptSignalLevel(StrEnum):
    STRONG = "STRONG"
    ADEQUATE = "ADEQUATE"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"


class QuickCheckSession(Base):
    __tablename__ = "quick_check_sessions"
    __table_args__ = (
        Index("ix_quick_check_sessions_teaching_plan", "teaching_plan_id"),
        Index("ix_quick_check_sessions_classroom", "classroom_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("practice_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    teaching_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("teaching_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    classroom_id: Mapped[UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    practice_session: Mapped["PracticeSession"] = relationship()
    teaching_plan: Mapped["TeachingPlan"] = relationship()
    classroom: Mapped["Classroom"] = relationship()
    questions: Mapped[list["QuickCheckQuestion"]] = relationship(
        back_populates="quick_check_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuickCheckQuestion.order_index",
    )


class QuickCheckQuestion(Base):
    __tablename__ = "quick_check_questions"
    __table_args__ = (
        UniqueConstraint(
            "quick_check_id",
            "question_id",
            name="uq_quick_check_questions_quick_check_question",
        ),
        UniqueConstraint(
            "quick_check_id",
            "order_index",
            name="uq_quick_check_questions_quick_check_order",
        ),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
        Index("ix_quick_check_questions_quick_check_id", "quick_check_id"),
        Index("ix_quick_check_questions_question_id", "question_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quick_check_id: Mapped[UUID] = mapped_column(
        ForeignKey("quick_check_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"),
        nullable=True,
    )
    target_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    target_role: Mapped[QuickCheckQuestionRole] = mapped_column(
        Enum(
            QuickCheckQuestionRole,
            native_enum=False,
            create_constraint=True,
            name="quick_check_question_role",
        ),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    quick_check_session: Mapped[QuickCheckSession] = relationship(back_populates="questions")
    question: Mapped["Question"] = relationship()
    target_problem_type: Mapped["ProblemType | None"] = relationship()
    target_concept: Mapped["Concept | None"] = relationship()
