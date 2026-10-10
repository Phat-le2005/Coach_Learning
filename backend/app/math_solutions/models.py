"""Isolated step-by-step math solution persistence (STEP-ARCH-01).

No routers are registered and no learning evidence is emitted in this module.
All grading and ownership enforcement are responsibilities of later services.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

JsonDocument = JSON().with_variant(JSONB, "postgresql")


class SolutionRubric(Base):
    __tablename__ = "math_solution_rubrics"
    __table_args__ = (
        CheckConstraint("(question_id IS NOT NULL AND assignment_material_item_id IS NULL) OR (question_id IS NULL AND assignment_material_item_id IS NOT NULL)", name="target_exclusive"),
        CheckConstraint("rubric_version >= 1", name="version_positive"),
        CheckConstraint("max_score > 0", name="max_score_positive"),
        CheckConstraint("status IN ('DRAFT','APPROVED','ARCHIVED')", name="status_allowed"),
        UniqueConstraint("question_id", "rubric_version", name="uq_math_rubric_question_version"),
        UniqueConstraint("assignment_material_item_id", "rubric_version", name="uq_math_rubric_material_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    question_id: Mapped[UUID | None] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    assignment_material_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("assignment_material_items.id", ondelete="RESTRICT"))
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SolutionAttempt(Base):
    __tablename__ = "math_solution_attempts"
    __table_args__ = (
        CheckConstraint("source_kind IN ('CANONICAL','TEACHER_MATERIAL')", name="source_kind_allowed"),
        CheckConstraint("context_type IN ('SELF_PRACTICE','CLASSROOM_ASSIGNMENT')", name="context_allowed"),
        CheckConstraint("mode IN ('GUIDED_LEARNING','INDEPENDENT_SOLUTION')", name="mode_allowed"),
        CheckConstraint("status IN ('DRAFT','IN_PROGRESS','SUBMITTED','EVALUATED','ABANDONED')", name="status_allowed"),
        CheckConstraint("attempt_revision_number >= 1", name="revision_positive"),
        CheckConstraint("total_score IS NULL OR total_score BETWEEN 0 AND 1", name="score_range"),
        CheckConstraint(
            "(source_kind = 'CANONICAL' AND question_id IS NOT NULL AND assignment_material_item_id IS NULL AND student_assignment_material_item_id IS NULL) OR "
            "(source_kind = 'TEACHER_MATERIAL' AND question_id IS NULL AND assignment_material_item_id IS NOT NULL AND student_assignment_material_item_id IS NOT NULL)",
            name="source_exclusive",
        ),
        CheckConstraint(
            "(context_type='SELF_PRACTICE' AND practice_session_id IS NOT NULL AND assignment_id IS NULL AND student_assignment_id IS NULL AND assignment_student_question_id IS NULL AND source_kind='CANONICAL') OR "
            "(context_type='CLASSROOM_ASSIGNMENT' AND practice_session_id IS NULL AND assignment_id IS NOT NULL AND student_assignment_id IS NOT NULL AND "
            "((source_kind='CANONICAL' AND assignment_student_question_id IS NOT NULL) OR (source_kind='TEACHER_MATERIAL' AND assignment_student_question_id IS NULL)))",
            name="context_alignment",
        ),
        UniqueConstraint("student_id", "create_idempotency_key", name="uq_math_attempt_create_key"),
        Index("ix_math_attempt_student_started", "student_id", "started_at"),
        Index("ix_math_attempt_assignment_student", "assignment_id", "student_id"),
        Index("ix_math_attempt_question_status", "question_id", "status"),
        Index("ix_math_attempt_material_status", "assignment_material_item_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="RESTRICT"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    context_type: Mapped[str] = mapped_column(String(32), nullable=False)
    question_id: Mapped[UUID | None] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    assignment_material_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("assignment_material_items.id", ondelete="RESTRICT"))
    student_assignment_material_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("student_assignment_material_items.id", ondelete="RESTRICT"))
    assignment_student_question_id: Mapped[UUID | None] = mapped_column(ForeignKey("assignment_student_questions.id", ondelete="RESTRICT"))
    practice_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("practice_sessions.id", ondelete="RESTRICT"))
    assignment_id: Mapped[UUID | None] = mapped_column(ForeignKey("assignments.id", ondelete="RESTRICT"))
    student_assignment_id: Mapped[UUID | None] = mapped_column(ForeignKey("student_assignments.id", ondelete="RESTRICT"))
    rubric_id: Mapped[UUID | None] = mapped_column(ForeignKey("math_solution_rubrics.id", ondelete="RESTRICT"))
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    attempt_revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    create_idempotency_key: Mapped[str | None] = mapped_column(String(100))
    total_score: Mapped[float | None] = mapped_column(Float)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SolutionStep(Base):
    __tablename__ = "math_solution_steps"
    __table_args__ = (
        CheckConstraint("step_index >= 1", name="index_positive"),
        CheckConstraint("step_type IN ('ASSUMPTION','DERIVATIVE_CALCULATION','ROOT_FINDING','SIGN_TABLE','VARIATION_TABLE','CONCLUSION','EXPLANATION','CUSTOM')", name="type_allowed"),
        CheckConstraint("(is_deleted = true AND status = 'DELETED') OR (is_deleted = false AND status IN ('DRAFT','ACTIVE'))", name="deleted_consistency"),
        Index("uq_math_solution_step_active_index", "attempt_id", "step_index", unique=True, postgresql_where=text("is_deleted = false"), sqlite_where=text("is_deleted = false")),
        Index("ix_math_solution_steps_attempt", "attempt_id", "step_index"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("math_solution_attempts.id", ondelete="CASCADE"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    content_latex: Mapped[str | None] = mapped_column(Text)
    explanation_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class StepRevision(Base):
    __tablename__ = "math_step_revisions"
    __table_args__ = (
        UniqueConstraint("step_id", "step_revision_number", name="uq_math_step_revision_number"),
        CheckConstraint("step_revision_number >= 1", name="revision_positive"),
        CheckConstraint("step_index_at_revision >= 1", name="index_positive"),
        CheckConstraint("change_reason IN ('STUDENT_EDIT','STUDENT_REORDER','AUTOSAVE','ROLLBACK','STUDENT_DELETE','STUDENT_RESTORE')", name="reason_allowed"),
        Index("ix_math_step_revisions_step_time", "step_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    step_id: Mapped[UUID] = mapped_column(ForeignKey("math_solution_steps.id", ondelete="RESTRICT"), nullable=False)
    step_revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_index_at_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_latex: Mapped[str | None] = mapped_column(Text)
    explanation_text: Mapped[str | None] = mapped_column(Text)
    artifact_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)
    change_reason: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MathArtifact(Base):
    __tablename__ = "math_artifacts"
    __table_args__ = (
        CheckConstraint("artifact_type IN ('SIGN_TABLE','VARIATION_TABLE','INTERVAL_SET','SYSTEM_OF_EQUATIONS')", name="type_allowed"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    step_revision_id: Mapped[UUID] = mapped_column(ForeignKey("math_step_revisions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)


class StepEvaluation(Base):
    __tablename__ = "math_step_evaluations"
    __table_args__ = (
        CheckConstraint("evaluator_type IN ('DETERMINISTIC_RULES','AI_HEURISTIC','TEACHER')", name="evaluator_allowed"),
        CheckConstraint("math_validity IN ('VALID','INVALID','UNDETERMINED','NEEDS_REVIEW')", name="validity_allowed"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_range"),
        Index("ix_math_step_evaluation_revision", "step_revision_id", "evaluated_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    step_revision_id: Mapped[UUID] = mapped_column(ForeignKey("math_step_revisions.id", ondelete="RESTRICT"), nullable=False)
    rubric_id: Mapped[UUID | None] = mapped_column(ForeignKey("math_solution_rubrics.id", ondelete="RESTRICT"))
    misconception_definition_id: Mapped[UUID | None] = mapped_column(ForeignKey("misconception_definitions.id", ondelete="RESTRICT"))
    evaluator_type: Mapped[str] = mapped_column(String(24), nullable=False)
    math_validity: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    error_detected: Mapped[bool | None] = mapped_column(Boolean)
    error_description: Mapped[str | None] = mapped_column(Text)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SolutionFeedback(Base):
    __tablename__ = "math_solution_feedbacks"
    __table_args__ = (
        CheckConstraint("feedback_type IN ('REFERENCE_HINT','SOCRATIC_QUESTION','VERIFICATION_ALERT','ERROR_CORRECTION')", name="type_allowed"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("math_solution_attempts.id", ondelete="RESTRICT"), nullable=False)
    step_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("math_step_revisions.id", ondelete="SET NULL"))
    feedback_type: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_reference_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvaluationDecision(Base):
    __tablename__ = "math_evaluation_decisions"
    __table_args__ = (
        CheckConstraint("decision_source IN ('AUTOMATED_CONSENSUS','TEACHER_REVIEW','AUDIT_APPROVED')", name="source_allowed"),
        CheckConstraint("final_score BETWEEN 0 AND 1", name="score_range"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("math_solution_attempts.id", ondelete="RESTRICT"), nullable=False, unique=True)
    rubric_id: Mapped[UUID | None] = mapped_column(ForeignKey("math_solution_rubrics.id", ondelete="RESTRICT"))
    decision_source: Mapped[str] = mapped_column(String(24), nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confirmed_misconceptions: Mapped[list[str]] = mapped_column(JsonDocument, nullable=False, default=list)
    learning_evidence_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("learning_evidence_events.id", ondelete="RESTRICT"), unique=True)
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvaluationOverride(Base):
    __tablename__ = "math_evaluation_overrides"
    __table_args__ = (
        CheckConstraint("previous_score BETWEEN 0 AND 1 AND new_score BETWEEN 0 AND 1", name="scores_range"),
        CheckConstraint("override_version >= 1", name="version_positive"),
        CheckConstraint("projection_status IN ('PENDING','APPLIED','REJECTED')", name="projection_allowed"),
        UniqueConstraint("decision_id", "override_version", name="uq_math_override_decision_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(ForeignKey("math_evaluation_decisions.id", ondelete="RESTRICT"), nullable=False)
    teacher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    override_version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_score: Mapped[float] = mapped_column(Float, nullable=False)
    new_score: Mapped[float] = mapped_column(Float, nullable=False)
    previous_is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    new_is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    override_reason: Mapped[str] = mapped_column(Text, nullable=False)
    projection_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SolutionOperation(Base):
    __tablename__ = "math_solution_operations"
    __table_args__ = (
        UniqueConstraint("attempt_id", "client_action_id", name="uq_math_operation_attempt_action"),
        CheckConstraint("length(request_hash) = 64", name="hash_length"),
        CheckConstraint("result_attempt_revision >= 1", name="revision_positive"),
        CheckConstraint("operation_type IN ('ADD_STEP','UPDATE_STEP','DELETE_STEP','RESTORE_STEP','REORDER_STEPS','ROLLBACK_STEP','SUBMIT')", name="type_allowed"),
        Index("ix_math_operations_attempt_created", "attempt_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("math_solution_attempts.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    client_action_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_attempt_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    response_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
