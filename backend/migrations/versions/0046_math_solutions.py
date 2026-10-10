"""Create isolated math solution schema (10 tables; no evidence changes).

Revision ID: 0046_math_solutions
Revises: 0045_teacher_analytics_indexes
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0046_math_solutions"
down_revision: str | Sequence[str] | None = "0045_teacher_analytics_indexes"
branch_labels = None
depends_on = None

JSON_DOC = sa.JSON().with_variant(JSONB, "postgresql")


def uid(name, ref=None, ondelete="RESTRICT", nullable=True, **kw):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(ref, ondelete=ondelete) if ref else sa.Uuid(), nullable=nullable, **kw) if ref else sa.Column(name, sa.Uuid(), nullable=nullable, **kw)


def created():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def check(expr, name):
    return sa.CheckConstraint(expr, name=name)


def upgrade() -> None:
    op.create_table("math_solution_rubrics",
        uid("id", nullable=False, primary_key=True),
        uid("question_id", "questions.id"),
        uid("assignment_material_item_id", "assignment_material_items.id"),
        sa.Column("rubric_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("criteria", JSON_DOC, nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        uid("approved_by", "users.id"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        created(),
        check("(question_id IS NOT NULL AND assignment_material_item_id IS NULL) OR (question_id IS NULL AND assignment_material_item_id IS NOT NULL)", "target_exclusive"),
        check("rubric_version >= 1", "version_positive"),
        check("max_score > 0", "max_score_positive"),
        check("status IN ('DRAFT','APPROVED','ARCHIVED')", "status_allowed"),
        sa.UniqueConstraint("question_id","rubric_version",name="uq_math_rubric_question_version"),
        sa.UniqueConstraint("assignment_material_item_id","rubric_version",name="uq_math_rubric_material_version"),
    )
    op.create_table("math_solution_attempts",
        uid("id", nullable=False, primary_key=True),
        uid("student_id", "student_profiles.id", nullable=False),
        sa.Column("source_kind", sa.String(24), nullable=False),
        sa.Column("context_type", sa.String(32), nullable=False),
        uid("question_id","questions.id"),
        uid("assignment_material_item_id","assignment_material_items.id"),
        uid("student_assignment_material_item_id","student_assignment_material_items.id"),
        uid("assignment_student_question_id","assignment_student_questions.id"),
        uid("practice_session_id","practice_sessions.id"),
        uid("assignment_id","assignments.id"),
        uid("student_assignment_id","student_assignments.id"),
        uid("rubric_id","math_solution_rubrics.id"),
        sa.Column("mode",sa.String(32),nullable=False),
        sa.Column("status",sa.String(20),nullable=False,server_default="DRAFT"),
        sa.Column("attempt_revision_number",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("create_idempotency_key",sa.String(100)),
        sa.Column("total_score",sa.Float()),
        sa.Column("is_correct",sa.Boolean()),
        sa.Column("started_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("submitted_at",sa.DateTime(timezone=True)),
        sa.Column("evaluated_at",sa.DateTime(timezone=True)),
        created(),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        check("source_kind IN ('CANONICAL','TEACHER_MATERIAL')","source_kind_allowed"),
        check("context_type IN ('SELF_PRACTICE','CLASSROOM_ASSIGNMENT')","context_allowed"),
        check("mode IN ('GUIDED_LEARNING','INDEPENDENT_SOLUTION')","mode_allowed"),
        check("status IN ('DRAFT','IN_PROGRESS','SUBMITTED','EVALUATED','ABANDONED')","status_allowed"),
        check("attempt_revision_number >= 1","revision_positive"),
        check("total_score IS NULL OR total_score BETWEEN 0 AND 1","score_range"),
        check("(source_kind = 'CANONICAL' AND question_id IS NOT NULL AND assignment_material_item_id IS NULL AND student_assignment_material_item_id IS NULL) OR (source_kind = 'TEACHER_MATERIAL' AND question_id IS NULL AND assignment_material_item_id IS NOT NULL AND student_assignment_material_item_id IS NOT NULL)","source_exclusive"),
        check("(context_type='SELF_PRACTICE' AND practice_session_id IS NOT NULL AND assignment_id IS NULL AND student_assignment_id IS NULL AND assignment_student_question_id IS NULL AND source_kind='CANONICAL') OR (context_type='CLASSROOM_ASSIGNMENT' AND practice_session_id IS NULL AND assignment_id IS NOT NULL AND student_assignment_id IS NOT NULL AND ((source_kind='CANONICAL' AND assignment_student_question_id IS NOT NULL) OR (source_kind='TEACHER_MATERIAL' AND assignment_student_question_id IS NULL)))","context_alignment"),
        sa.UniqueConstraint("student_id","create_idempotency_key",name="uq_math_attempt_create_key"),
    )
    op.create_index("ix_math_attempt_student_started","math_solution_attempts",["student_id","started_at"])
    op.create_index("ix_math_attempt_assignment_student","math_solution_attempts",["assignment_id","student_id"])
    op.create_index("ix_math_attempt_question_status","math_solution_attempts",["question_id","status"])
    op.create_index("ix_math_attempt_material_status","math_solution_attempts",["assignment_material_item_id","status"])
    op.create_table("math_solution_steps",
        uid("id",nullable=False,primary_key=True),
        uid("attempt_id","math_solution_attempts.id",ondelete="CASCADE",nullable=False),
        sa.Column("step_index",sa.Integer(),nullable=False),
        sa.Column("step_type",sa.String(40),nullable=False),
        sa.Column("status",sa.String(16),nullable=False,server_default="ACTIVE"),
        sa.Column("is_deleted",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("content_latex",sa.Text()),
        sa.Column("explanation_text",sa.Text()),
        created(),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        check("step_index >= 1","index_positive"),
        check("step_type IN ('ASSUMPTION','DERIVATIVE_CALCULATION','ROOT_FINDING','SIGN_TABLE','VARIATION_TABLE','CONCLUSION','EXPLANATION','CUSTOM')","type_allowed"),
        check("(is_deleted = true AND status = 'DELETED') OR (is_deleted = false AND status IN ('DRAFT','ACTIVE'))","deleted_consistency"),
    )
    op.create_index("uq_math_solution_step_active_index","math_solution_steps",["attempt_id","step_index"],unique=True,postgresql_where=sa.text("is_deleted = false"),sqlite_where=sa.text("is_deleted = false"))
    op.create_index("ix_math_solution_steps_attempt","math_solution_steps",["attempt_id","step_index"])
    op.create_table("math_step_revisions",
        uid("id",nullable=False,primary_key=True),
        uid("step_id","math_solution_steps.id",nullable=False),
        sa.Column("step_revision_number",sa.Integer(),nullable=False),
        sa.Column("step_index_at_revision",sa.Integer(),nullable=False),
        sa.Column("content_latex",sa.Text()),
        sa.Column("explanation_text",sa.Text()),
        sa.Column("artifact_snapshot",JSON_DOC),
        sa.Column("change_reason",sa.String(24),nullable=False),
        created(),
        sa.UniqueConstraint("step_id","step_revision_number",name="uq_math_step_revision_number"),
        check("step_revision_number >= 1","revision_positive"),
        check("step_index_at_revision >= 1","index_positive"),
        check("change_reason IN ('STUDENT_EDIT','STUDENT_REORDER','AUTOSAVE','ROLLBACK','STUDENT_DELETE','STUDENT_RESTORE')","reason_allowed"),
    )
    op.create_index("ix_math_step_revisions_step_time","math_step_revisions",["step_id","created_at"])
    op.create_table("math_artifacts",
        uid("id",nullable=False,primary_key=True),
        uid("step_revision_id","math_step_revisions.id",nullable=False,unique=True),
        sa.Column("artifact_type",sa.String(32),nullable=False),
        sa.Column("payload",JSON_DOC,nullable=False),
        check("artifact_type IN ('SIGN_TABLE','VARIATION_TABLE','INTERVAL_SET','SYSTEM_OF_EQUATIONS')","type_allowed"),
    )
    op.create_table("math_step_evaluations",
        uid("id",nullable=False,primary_key=True),
        uid("step_revision_id","math_step_revisions.id",nullable=False),
        uid("rubric_id","math_solution_rubrics.id"),
        uid("misconception_definition_id","misconception_definitions.id"),
        sa.Column("evaluator_type",sa.String(24),nullable=False),
        sa.Column("math_validity",sa.String(20),nullable=False),
        sa.Column("score",sa.Float()),
        sa.Column("confidence",sa.Float()),
        sa.Column("error_detected",sa.Boolean()),
        sa.Column("error_description",sa.Text()),
        sa.Column("evidence_quote",sa.Text()),
        sa.Column("evaluated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        check("evaluator_type IN ('DETERMINISTIC_RULES','AI_HEURISTIC','TEACHER')","evaluator_allowed"),
        check("math_validity IN ('VALID','INVALID','UNDETERMINED','NEEDS_REVIEW')","validity_allowed"),
        check("score IS NULL OR score BETWEEN 0 AND 1","score_range"),
        check("confidence IS NULL OR confidence BETWEEN 0 AND 1","confidence_range"),
    )
    op.create_index("ix_math_step_evaluation_revision","math_step_evaluations",["step_revision_id","evaluated_at"])
    op.create_table("math_solution_feedbacks",
        uid("id",nullable=False,primary_key=True),
        uid("attempt_id","math_solution_attempts.id",nullable=False),
        uid("step_revision_id","math_step_revisions.id",ondelete="SET NULL"),
        sa.Column("feedback_type",sa.String(24),nullable=False),
        sa.Column("content",sa.Text(),nullable=False),
        sa.Column("is_reference_only",sa.Boolean(),nullable=False,server_default=sa.true()),
        created(),
        check("feedback_type IN ('REFERENCE_HINT','SOCRATIC_QUESTION','VERIFICATION_ALERT','ERROR_CORRECTION')","type_allowed"),
    )
    op.create_table("math_evaluation_decisions",
        uid("id",nullable=False,primary_key=True),
        uid("attempt_id","math_solution_attempts.id",nullable=False,unique=True),
        uid("rubric_id","math_solution_rubrics.id"),
        sa.Column("decision_source",sa.String(24),nullable=False),
        sa.Column("final_score",sa.Float(),nullable=False),
        sa.Column("is_correct",sa.Boolean(),nullable=False),
        sa.Column("confirmed_misconceptions",JSON_DOC,nullable=False),
        uid("learning_evidence_event_id","learning_evidence_events.id",unique=True),
        uid("decided_by","users.id"),
        sa.Column("decided_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        check("decision_source IN ('AUTOMATED_CONSENSUS','TEACHER_REVIEW','AUDIT_APPROVED')","source_allowed"),
        check("final_score BETWEEN 0 AND 1","score_range"),
    )
    op.create_table("math_evaluation_overrides",
        uid("id",nullable=False,primary_key=True),
        uid("decision_id","math_evaluation_decisions.id",nullable=False),
        uid("teacher_id","users.id",nullable=False),
        sa.Column("override_version",sa.Integer(),nullable=False),
        sa.Column("previous_score",sa.Float(),nullable=False),
        sa.Column("new_score",sa.Float(),nullable=False),
        sa.Column("previous_is_correct",sa.Boolean(),nullable=False),
        sa.Column("new_is_correct",sa.Boolean(),nullable=False),
        sa.Column("override_reason",sa.Text(),nullable=False),
        sa.Column("projection_status",sa.String(16),nullable=False,server_default="PENDING"),
        created(),
        check("previous_score BETWEEN 0 AND 1 AND new_score BETWEEN 0 AND 1","scores_range"),
        check("override_version >= 1","version_positive"),
        check("projection_status IN ('PENDING','APPLIED','REJECTED')","projection_allowed"),
        sa.UniqueConstraint("decision_id","override_version",name="uq_math_override_decision_version"),
    )
    op.create_table("math_solution_operations",
        uid("id",nullable=False,primary_key=True),
        uid("attempt_id","math_solution_attempts.id",nullable=False),
        uid("actor_user_id","users.id",nullable=False),
        sa.Column("client_action_id",sa.Uuid(),nullable=False),
        sa.Column("operation_type",sa.String(20),nullable=False),
        sa.Column("request_hash",sa.String(64),nullable=False),
        sa.Column("result_attempt_revision",sa.Integer(),nullable=False),
        sa.Column("response_snapshot",JSON_DOC,nullable=False),
        created(),
        sa.UniqueConstraint("attempt_id","client_action_id",name="uq_math_operation_attempt_action"),
        check("length(request_hash) = 64","hash_length"),
        check("result_attempt_revision >= 1","revision_positive"),
        check("operation_type IN ('ADD_STEP','UPDATE_STEP','DELETE_STEP','RESTORE_STEP','REORDER_STEPS','ROLLBACK_STEP','SUBMIT')","type_allowed"),
    )
    op.create_index("ix_math_operations_attempt_created","math_solution_operations",["attempt_id","created_at"])


def downgrade() -> None:
    op.drop_index("ix_math_operations_attempt_created",table_name="math_solution_operations")
    op.drop_table("math_solution_operations")
    op.drop_table("math_evaluation_overrides")
    op.drop_table("math_evaluation_decisions")
    op.drop_table("math_solution_feedbacks")
    op.drop_index("ix_math_step_evaluation_revision",table_name="math_step_evaluations")
    op.drop_table("math_step_evaluations")
    op.drop_table("math_artifacts")
    op.drop_index("ix_math_step_revisions_step_time",table_name="math_step_revisions")
    op.drop_table("math_step_revisions")
    op.drop_index("ix_math_solution_steps_attempt",table_name="math_solution_steps")
    op.drop_index("uq_math_solution_step_active_index",table_name="math_solution_steps")
    op.drop_table("math_solution_steps")
    for name in ("ix_math_attempt_material_status","ix_math_attempt_question_status","ix_math_attempt_assignment_student","ix_math_attempt_student_started"):
        op.drop_index(name,table_name="math_solution_attempts")
    op.drop_table("math_solution_attempts")
    op.drop_table("math_solution_rubrics")
