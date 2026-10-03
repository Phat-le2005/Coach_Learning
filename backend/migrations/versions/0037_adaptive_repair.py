"""Add persistent adaptive verified-root-cause repair state.

Revision ID: 0037_adaptive_repair
Revises: 0036_root_cause_verification_hardening
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0037_adaptive_repair"
down_revision: str | Sequence[str] | None = "0036_root_cause_verification_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adaptive_repair_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("practice_session_id", sa.Uuid(), sa.ForeignKey("practice_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Uuid(), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("diagnosis_id", sa.Uuid(), sa.ForeignKey("root_cause_diagnoses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("verification_id", sa.Uuid(), sa.ForeignKey("root_cause_verifications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("verification_target_id", sa.Uuid(), sa.ForeignKey("root_cause_verification_targets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_type", sa.Enum("CONCEPT", "PROBLEM_TYPE", "MISCONCEPTION", name="adaptive_repair_target_type", native_enum=False), nullable=False),
        sa.Column("target_concept_id", sa.Uuid(), sa.ForeignKey("concepts.id", ondelete="RESTRICT")),
        sa.Column("target_problem_type_id", sa.Uuid(), sa.ForeignKey("problem_types.id", ondelete="RESTRICT")),
        sa.Column("misconception_definition_id", sa.Uuid(), sa.ForeignKey("misconception_definitions.id", ondelete="RESTRICT")),
        sa.Column("target_name", sa.String(255)),
        sa.Column("target_code", sa.String(100)),
        sa.Column("status", sa.Enum("ACTIVE", "COMPLETED", name="adaptive_repair_status", native_enum=False), nullable=False),
        sa.Column("phase", sa.Enum("FOUNDATION", "GUIDED", "TARGET_PRACTICE", "FINAL_RECHECK", name="adaptive_repair_phase", native_enum=False), nullable=False),
        sa.Column("outcome", sa.Enum("PENDING", "RESOLVED", "NEEDS_MORE_PRACTICE", "BANK_EXHAUSTED", name="adaptive_repair_outcome", native_enum=False), nullable=False),
        sa.Column("initial_difficulty", sa.Float(), nullable=False),
        sa.Column("current_difficulty", sa.Float(), nullable=False),
        sa.Column("target_exit_difficulty", sa.Float(), nullable=False),
        sa.Column("verification_average_score", sa.Float()),
        sa.Column("attempted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_wrong", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_questions", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("practice_session_id", name="uq_adaptive_repair_practice_session"),
        sa.UniqueConstraint("verification_target_id", name="uq_adaptive_repair_verification_target"),
        sa.CheckConstraint("initial_difficulty BETWEEN 0 AND 1", name="ck_adaptive_repair_sessions_initial_difficulty_range"),
        sa.CheckConstraint("current_difficulty BETWEEN 0 AND 1", name="ck_adaptive_repair_sessions_current_difficulty_range"),
        sa.CheckConstraint("target_exit_difficulty BETWEEN 0 AND 1", name="ck_adaptive_repair_sessions_target_exit_difficulty_range"),
        sa.CheckConstraint("verification_average_score IS NULL OR verification_average_score BETWEEN 0 AND 1", name="ck_adaptive_repair_sessions_verification_average_score_range"),
        sa.CheckConstraint("attempted_count >= 0", name="ck_adaptive_repair_sessions_attempted_count_nonnegative"),
        sa.CheckConstraint("correct_count >= 0", name="ck_adaptive_repair_sessions_correct_count_nonnegative"),
        sa.CheckConstraint("correct_count <= attempted_count", name="ck_adaptive_repair_sessions_correct_count_not_exceed_attempted"),
        sa.CheckConstraint("consecutive_correct >= 0", name="ck_adaptive_repair_sessions_consecutive_correct_nonnegative"),
        sa.CheckConstraint("consecutive_wrong >= 0", name="ck_adaptive_repair_sessions_consecutive_wrong_nonnegative"),
        sa.CheckConstraint("max_questions > 0", name="ck_adaptive_repair_sessions_max_questions_positive"),
        sa.CheckConstraint("(status = 'ACTIVE' AND outcome = 'PENDING' AND completed_at IS NULL) OR (status = 'COMPLETED' AND outcome <> 'PENDING' AND completed_at IS NOT NULL)", name="ck_adaptive_repair_sessions_completion_consistency"),
    )
    op.create_index("ix_adaptive_repair_student_status", "adaptive_repair_sessions", ["student_id", "status"])
    op.create_index("ix_adaptive_repair_diagnosis", "adaptive_repair_sessions", ["diagnosis_id"])

    op.create_table(
        "adaptive_repair_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("adaptive_repair_session_id", sa.Uuid(), sa.ForeignKey("adaptive_repair_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Uuid(), sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("FOUNDATION", "GUIDED", "PRACTICE", "FINAL_RECHECK", name="adaptive_repair_item_role", native_enum=False), nullable=False),
        sa.Column("desired_difficulty", sa.Float(), nullable=False),
        sa.Column("selection_score", sa.Float()),
        sa.Column("selection_reason", sa.String(100), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("question_attempts.id", ondelete="SET NULL")),
        sa.Column("difficulty_before", sa.Float(), nullable=False),
        sa.Column("difficulty_after", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("adaptive_repair_session_id", "order_index", name="uq_adaptive_repair_item_order"),
        sa.UniqueConstraint("adaptive_repair_session_id", "question_id", name="uq_adaptive_repair_item_question"),
        sa.UniqueConstraint("attempt_id", name="uq_adaptive_repair_item_attempt"),
        sa.CheckConstraint("order_index > 0", name="ck_adaptive_repair_items_order_index_positive"),
        sa.CheckConstraint("desired_difficulty BETWEEN 0 AND 1", name="ck_adaptive_repair_items_desired_difficulty_range"),
        sa.CheckConstraint("difficulty_before BETWEEN 0 AND 1", name="ck_adaptive_repair_items_difficulty_before_range"),
        sa.CheckConstraint("difficulty_after IS NULL OR difficulty_after BETWEEN 0 AND 1", name="ck_adaptive_repair_items_difficulty_after_range"),
    )
    op.create_index("ix_adaptive_repair_item_session", "adaptive_repair_items", ["adaptive_repair_session_id"])

    op.create_table(
        "adaptive_repair_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("adaptive_repair_session_id", sa.Uuid(), sa.ForeignKey("adaptive_repair_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("adaptive_repair_item_id", sa.Uuid(), sa.ForeignKey("adaptive_repair_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_index", sa.Integer(), nullable=False),
        sa.Column("phase_before", sa.Enum("FOUNDATION", "GUIDED", "TARGET_PRACTICE", "FINAL_RECHECK", name="adaptive_repair_decision_phase_before", native_enum=False), nullable=False),
        sa.Column("phase_after", sa.Enum("FOUNDATION", "GUIDED", "TARGET_PRACTICE", "FINAL_RECHECK", name="adaptive_repair_decision_phase_after", native_enum=False), nullable=False),
        sa.Column("difficulty_before", sa.Float(), nullable=False),
        sa.Column("difficulty_after", sa.Float(), nullable=False),
        sa.Column("reason_code", sa.Enum("CORRECT_ADVANCE_DIFFICULTY", "CORRECT_WITH_HINT_SMALL_ADVANCE", "WRONG_REDUCE_DIFFICULTY", "REPEATED_WRONG_ENTER_GUIDED", "RECOVERED_EXIT_GUIDED", "READY_FOR_FINAL_RECHECK", "FINAL_RECHECK_PASSED", "FINAL_RECHECK_FAILED", "MAX_QUESTIONS_REACHED", "QUESTION_BANK_EXHAUSTED", name="adaptive_repair_decision_reason", native_enum=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("adaptive_repair_item_id", name="uq_adaptive_repair_decision_item"),
        sa.UniqueConstraint("adaptive_repair_session_id", "decision_index", name="uq_adaptive_repair_decision_index"),
        sa.CheckConstraint("decision_index > 0", name="ck_adaptive_repair_decisions_decision_index_positive"),
        sa.CheckConstraint("difficulty_before BETWEEN 0 AND 1", name="ck_adaptive_repair_decisions_difficulty_before_range"),
        sa.CheckConstraint("difficulty_after BETWEEN 0 AND 1", name="ck_adaptive_repair_decisions_difficulty_after_range"),
    )
    op.create_index("ix_adaptive_repair_decision_session", "adaptive_repair_decisions", ["adaptive_repair_session_id"])


def downgrade() -> None:
    op.drop_index("ix_adaptive_repair_decision_session", table_name="adaptive_repair_decisions")
    op.drop_table("adaptive_repair_decisions")
    op.drop_index("ix_adaptive_repair_item_session", table_name="adaptive_repair_items")
    op.drop_table("adaptive_repair_items")
    op.drop_index("ix_adaptive_repair_diagnosis", table_name="adaptive_repair_sessions")
    op.drop_index("ix_adaptive_repair_student_status", table_name="adaptive_repair_sessions")
    op.drop_table("adaptive_repair_sessions")
