from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.questions.models import Question


class HintLevel(StrEnum):
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"
    LEVEL_4 = "LEVEL_4"

    @property
    def number(self) -> int:
        return int(self.value.rsplit("_", maxsplit=1)[1])


class HintSource(StrEnum):
    PREDEFINED = "PREDEFINED"
    AI = "AI"


class QuestionHint(Base):
    """Author-provided hint content stored in the Question Bank."""

    __tablename__ = "question_hints"
    __table_args__ = (
        CheckConstraint("length(trim(content)) > 0", name="content_not_blank"),
    )

    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    hint_level: Mapped[HintLevel] = mapped_column(
        Enum(
            HintLevel,
            native_enum=False,
            create_constraint=True,
            name="hint_level",
        ),
        primary_key=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    question: Mapped["Question"] = relationship(back_populates="hints")


class PracticeQuestionHint(Base):
    """Immutable record of a hint shown for a question in a practice session."""

    __tablename__ = "practice_question_hints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["practice_session_id", "student_id"],
            ["practice_sessions.id", "practice_sessions.student_id"],
            ondelete="CASCADE",
            name="fk_practice_question_hints_session_student",
        ),
        UniqueConstraint(
            "practice_session_id",
            "question_id",
            "hint_level",
            name="uq_practice_question_hints_session_question_level",
        ),
        UniqueConstraint(
            "practice_session_id",
            "question_id",
            "hint_count",
            name="uq_practice_question_hints_session_question_count",
        ),
        CheckConstraint(
            "hint_count BETWEEN 1 AND 4", name="hint_count_range"
        ),
        CheckConstraint("length(trim(content)) > 0", name="content_not_blank"),
        Index(
            "ix_practice_question_hints_session_question",
            "practice_session_id",
            "question_id",
        ),
        Index(
            "ix_practice_question_hints_student_created",
            "student_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    practice_session_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    student_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    hint_level: Mapped[HintLevel] = mapped_column(
        Enum(
            HintLevel,
            native_enum=False,
            create_constraint=True,
            name="hint_level",
        ),
        nullable=False,
    )
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False)
    hint_source: Mapped[HintSource] = mapped_column(
        Enum(
            HintSource,
            native_enum=False,
            create_constraint=True,
            name="hint_source",
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
