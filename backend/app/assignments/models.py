from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
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
from app.practice.models import EvaluationStatus
from app.questions.models import QuestionType
from app.teacher_materials.models import MaterialEvaluationMode

if TYPE_CHECKING:
    from app.classes.models import Classroom
    from app.concepts.models import Concept
    from app.curriculum.models import LearningOutcome, ProblemType
    from app.questions.models import Question
    from app.students.models import StudentProfile
    from app.subjects.models import Subject
    from app.users.models import User
    from app.teacher_materials.models import TeacherMaterialItem


class AssignmentType(StrEnum):
    SAME_SET = "SAME_SET"
    ADAPTIVE_SET = "ADAPTIVE_SET"


class AssignmentStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class StudentAssignmentStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("question_count > 0", name="question_count_positive"),
        Index("ix_assignments_classroom_status", "classroom_id", "status"),
        Index("ix_assignments_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    classroom_id: Mapped[UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    teaching_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teaching_plans.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_type: Mapped[AssignmentType] = mapped_column(
        Enum(
            AssignmentType,
            native_enum=False,
            create_constraint=True,
            name="assignment_type",
        ),
        nullable=False,
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(
            AssignmentStatus,
            native_enum=False,
            create_constraint=True,
            name="assignment_status",
        ),
        nullable=False,
        default=AssignmentStatus.DRAFT,
        server_default=AssignmentStatus.DRAFT.value,
    )
    question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    difficulty_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    classroom: Mapped["Classroom"] = relationship()
    subject: Mapped["Subject"] = relationship()
    creator: Mapped["User"] = relationship()

    learning_objectives: Mapped[list["AssignmentLearningObjective"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", passive_deletes=True
    )
    problem_types: Mapped[list["AssignmentProblemType"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", passive_deletes=True
    )
    concepts: Mapped[list["AssignmentConcept"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", passive_deletes=True
    )
    questions: Mapped[list["AssignmentQuestion"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssignmentQuestion.order_index",
    )
    material_items: Mapped[list["AssignmentMaterialItem"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", passive_deletes=True,
        order_by="AssignmentMaterialItem.order_index",
    )
    student_assignments: Mapped[list["StudentAssignment"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", passive_deletes=True
    )


class AssignmentLearningObjective(Base):
    __tablename__ = "assignment_learning_objectives"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "learning_outcome_id",
            name="uq_assignment_learning_objectives_assignment_id_learning_outcome_id",
        ),
        Index("ix_assignment_learning_objectives_assignment_id", "assignment_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    learning_outcome_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")

    assignment: Mapped[Assignment] = relationship(back_populates="learning_objectives")
    learning_outcome: Mapped["LearningOutcome"] = relationship()


class AssignmentProblemType(Base):
    __tablename__ = "assignment_problem_types"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "problem_type_id",
            name="uq_assignment_problem_types_assignment_id_problem_type_id",
        ),
        Index("ix_assignment_problem_types_assignment_id", "assignment_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")

    assignment: Mapped[Assignment] = relationship(back_populates="problem_types")
    problem_type: Mapped["ProblemType"] = relationship()


class AssignmentConcept(Base):
    __tablename__ = "assignment_concepts"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "concept_id",
            name="uq_assignment_concepts_assignment_id_concept_id",
        ),
        Index("ix_assignment_concepts_assignment_id", "assignment_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")

    assignment: Mapped[Assignment] = relationship(back_populates="concepts")
    concept: Mapped["Concept"] = relationship()


class AssignmentQuestion(Base):
    __tablename__ = "assignment_questions"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "question_id",
            name="uq_assignment_questions_assignment_id_question_id",
        ),
        Index("ix_assignment_questions_assignment_id", "assignment_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    assignment: Mapped[Assignment] = relationship(back_populates="questions")
    question: Mapped["Question"] = relationship()


class AssignmentMaterialItem(Base):
    __tablename__ = "assignment_material_items"
    __table_args__ = (
        UniqueConstraint("assignment_id", "teacher_material_item_id", name="uq_assignment_material_item"),
        UniqueConstraint("assignment_id", "order_index", name="uq_assignment_material_order"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    teacher_material_item_id: Mapped[UUID] = mapped_column(ForeignKey("teacher_material_items.id", ondelete="RESTRICT"), nullable=False)
    teacher_material_id: Mapped[UUID | None] = mapped_column(ForeignKey("teacher_materials.id", ondelete="RESTRICT"))
    source_content_hash: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str | None] = mapped_column(Text)
    question_type: Mapped[QuestionType | None] = mapped_column(Enum(QuestionType, native_enum=False, name="assignment_material_question_type"))
    correct_answer: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[float | None] = mapped_column(Float)
    evaluation_mode: Mapped[MaterialEvaluationMode | None] = mapped_column(Enum(MaterialEvaluationMode, native_enum=False, name="assignment_material_evaluation_mode"))
    snapshotted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment: Mapped[Assignment] = relationship(back_populates="material_items")
    teacher_material_item: Mapped["TeacherMaterialItem"] = relationship()
    options: Mapped[list["AssignmentMaterialItemOption"]] = relationship(cascade="all, delete-orphan", order_by="AssignmentMaterialItemOption.order_index")
    concept_mappings: Mapped[list["AssignmentMaterialItemConcept"]] = relationship(cascade="all, delete-orphan")
    problem_type_mappings: Mapped[list["AssignmentMaterialItemProblemType"]] = relationship(cascade="all, delete-orphan")
    learning_outcome_mappings: Mapped[list["AssignmentMaterialItemLearningOutcome"]] = relationship(cascade="all, delete-orphan")


class AssignmentMaterialItemOption(Base):
    __tablename__ = "assignment_material_item_options"
    __table_args__ = (UniqueConstraint("assignment_material_item_id", "label"), UniqueConstraint("assignment_material_item_id", "order_index"))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_material_item_id: Mapped[UUID] = mapped_column(ForeignKey("assignment_material_items.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class _AssignmentMaterialMapping:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_material_item_id: Mapped[UUID] = mapped_column(ForeignKey("assignment_material_items.id", ondelete="CASCADE"), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AssignmentMaterialItemConcept(_AssignmentMaterialMapping, Base):
    __tablename__ = "assignment_material_item_concepts"
    __table_args__ = (UniqueConstraint("assignment_material_item_id", "concept_id"),)
    concept_id: Mapped[UUID] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False)


class AssignmentMaterialItemProblemType(_AssignmentMaterialMapping, Base):
    __tablename__ = "assignment_material_item_problem_types"
    __table_args__ = (UniqueConstraint("assignment_material_item_id", "problem_type_id"),)
    problem_type_id: Mapped[UUID] = mapped_column(ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=False)


class AssignmentMaterialItemLearningOutcome(_AssignmentMaterialMapping, Base):
    __tablename__ = "assignment_material_item_learning_outcomes"
    __table_args__ = (UniqueConstraint("assignment_material_item_id", "learning_outcome_id"),)
    learning_outcome_id: Mapped[UUID] = mapped_column(ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), nullable=False)


class StudentAssignment(Base):
    __tablename__ = "student_assignments"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "student_id",
            name="uq_student_assignments_assignment_id_student_id",
        ),
        Index("ix_student_assignments_assignment_status", "assignment_id", "status"),
        Index("ix_student_assignments_student_id", "student_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[StudentAssignmentStatus] = mapped_column(
        Enum(
            StudentAssignmentStatus,
            native_enum=False,
            create_constraint=True,
            name="student_assignment_status",
        ),
        nullable=False,
        default=StudentAssignmentStatus.NOT_STARTED,
        server_default=StudentAssignmentStatus.NOT_STARTED.value,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    assignment: Mapped[Assignment] = relationship(back_populates="student_assignments")
    student: Mapped["StudentProfile"] = relationship()
    student_questions: Mapped[list["AssignmentStudentQuestion"]] = relationship(
        back_populates="student_assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssignmentStudentQuestion.order_index",
    )
    student_material_items: Mapped[list["StudentAssignmentMaterialItem"]] = relationship(
        back_populates="student_assignment", cascade="all, delete-orphan", passive_deletes=True,
        order_by="StudentAssignmentMaterialItem.order_index",
    )


class AssignmentStudentQuestion(Base):
    __tablename__ = "assignment_student_questions"
    __table_args__ = (
        UniqueConstraint(
            "student_assignment_id",
            "question_id",
            name="uq_assignment_student_questions_student_assignment_id_question_id",
        ),
        Index(
            "ix_assignment_student_questions_student_assignment_id",
            "student_assignment_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_assignments.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student_assignment: Mapped[StudentAssignment] = relationship(
        back_populates="student_questions"
    )
    question: Mapped["Question"] = relationship()


class StudentAssignmentMaterialItem(Base):
    __tablename__ = "student_assignment_material_items"
    __table_args__ = (
        UniqueConstraint("student_assignment_id", "teacher_material_item_id", name="uq_student_assignment_material_item"),
        UniqueConstraint("student_assignment_id", "assignment_material_item_id", name="uq_student_assignment_material_snapshot"),
        UniqueConstraint("student_assignment_id", "order_index", name="uq_student_assignment_material_order"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
        CheckConstraint("response_time_seconds IS NULL OR response_time_seconds > 0", name="response_time_positive"),
        CheckConstraint("hint_count >= 0", name="hint_count_nonnegative"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_assignment_id: Mapped[UUID] = mapped_column(ForeignKey("student_assignments.id", ondelete="CASCADE"), nullable=False)
    teacher_material_item_id: Mapped[UUID] = mapped_column(ForeignKey("teacher_material_items.id", ondelete="RESTRICT"), nullable=False)
    assignment_material_item_id: Mapped[UUID] = mapped_column(ForeignKey("assignment_material_items.id", ondelete="RESTRICT"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    student_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)
    response_time_seconds: Mapped[float | None] = mapped_column(Float)
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    evaluation_status: Mapped[EvaluationStatus] = mapped_column(Enum(EvaluationStatus, name="student_material_evaluation_status", native_enum=False), nullable=False)
    evaluation_details: Mapped[dict | None] = mapped_column(JSON)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graded_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    teacher_feedback: Mapped[str | None] = mapped_column(Text)
    student_assignment: Mapped[StudentAssignment] = relationship(back_populates="student_material_items")
    assignment_material_item: Mapped[AssignmentMaterialItem] = relationship()
    teacher_material_item: Mapped["TeacherMaterialItem"] = relationship()
