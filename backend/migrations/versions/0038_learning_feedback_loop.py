"""Add post-repair learning feedback loop and repair cycle tracking.

Revision ID: 0038_learning_feedback_loop
Revises: 0037_adaptive_repair
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0038_learning_feedback_loop"
down_revision: str | Sequence[str] | None = "0037_adaptive_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("adaptive_repair_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("repair_cycle_index", sa.Integer(), nullable=False, server_default="1"),
        )
        batch_op.add_column(
            sa.Column(
                "previous_adaptive_repair_session_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "adaptive_repair_sessions.id",
                    ondelete="SET NULL",
                    name="fk_adaptive_repair_previous_session",
                ),
                nullable=True,
            ),
        )
        batch_op.drop_constraint("uq_adaptive_repair_verification_target", type_="unique")
        batch_op.create_unique_constraint(
            "uq_adaptive_repair_target_cycle",
            ["verification_target_id", "repair_cycle_index"],
        )
        batch_op.create_check_constraint(
            "repair_cycle_index_positive",
            "repair_cycle_index >= 1",
        )

    op.create_table(
        "learning_feedback_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Uuid(), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "adaptive_repair_session_id",
            sa.Uuid(),
            sa.ForeignKey("adaptive_repair_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Enum(
                "RETURN_TO_CURRENT_LEARNING",
                "REVIEW_LATER",
                "RETRY_REPAIR",
                "COLLECT_MORE_EVIDENCE",
                "QUESTION_SUPPLY_GAP",
                "NO_ACTIVE_LEARNING",
                name="learning_feedback_action",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "reason_code",
            sa.Enum(
                "REPAIR_RESOLVED_REVIEW_SCHEDULED",
                "REPAIR_RESOLVED_TARGET_STABLE",
                "REPAIR_NEEDS_MORE_RETRY_AVAILABLE",
                "REPAIR_RETRY_LIMIT_REACHED",
                "REPAIR_BANK_EXHAUSTED",
                "REPAIR_NEEDS_MORE_NO_QUESTIONS",
                "CURRENT_LESSON_AVAILABLE",
                "NO_ACTIVE_TEACHING_PLAN",
                "NO_ACTIVE_LEARNING_PRIORITY",
                name="learning_feedback_reason_code",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sa.Enum("CONCEPT", "PROBLEM_TYPE", "MISCONCEPTION", name="learning_feedback_target_type", native_enum=False),
            nullable=True,
        ),
        sa.Column("target_concept_id", sa.Uuid(), sa.ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("target_problem_type_id", sa.Uuid(), sa.ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("recommended_question_id", sa.Uuid(), sa.ForeignKey("questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_schedule_id", sa.Uuid(), sa.ForeignKey("review_schedules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("repair_cycle_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("adaptive_repair_session_id", name="uq_learning_feedback_adaptive_repair_session"),
        sa.CheckConstraint("repair_cycle_index >= 1", name="ck_learning_feedback_decisions_repair_cycle_index_positive"),
    )
    op.create_index("ix_learning_feedback_student_subject", "learning_feedback_decisions", ["student_id", "subject_id"])
    op.create_index("ix_learning_feedback_session", "learning_feedback_decisions", ["adaptive_repair_session_id"])


def downgrade() -> None:
    op.drop_index("ix_learning_feedback_session", table_name="learning_feedback_decisions")
    op.drop_index("ix_learning_feedback_student_subject", table_name="learning_feedback_decisions")
    op.drop_table("learning_feedback_decisions")

    with op.batch_alter_table("adaptive_repair_sessions") as batch_op:
        batch_op.drop_constraint("ck_adaptive_repair_sessions_repair_cycle_index_positive", type_="check")
        batch_op.drop_constraint("uq_adaptive_repair_target_cycle", type_="unique")
        batch_op.create_unique_constraint(
            "uq_adaptive_repair_verification_target",
            ["verification_target_id"],
        )
        batch_op.drop_column("previous_adaptive_repair_session_id")
        batch_op.drop_column("repair_cycle_index")
