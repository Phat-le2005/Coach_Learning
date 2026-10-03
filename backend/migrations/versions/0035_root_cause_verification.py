"""Persist root-cause verification sessions, targets, and frozen probe items.

Revision ID: 0035_root_cause_verification
Revises: 0034_root_cause_diagnostics
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0035_root_cause_verification"
down_revision: str | Sequence[str] | None = "0034_root_cause_diagnostics"
branch_labels = None
depends_on = None

verification_statuses = (
    "PENDING",
    "ACTIVE",
    "COMPLETED",
    "UNAVAILABLE",
)

target_types = (
    "CONCEPT",
    "PROBLEM_TYPE",
    "MISCONCEPTION",
)

target_outcomes = (
    "PENDING",
    "SUPPORTED",
    "NOT_SUPPORTED",
    "INCONCLUSIVE",
    "UNAVAILABLE",
)


def upgrade() -> None:
    with op.batch_alter_table("practice_sessions") as batch_op:
        batch_op.drop_constraint("practice_session_type", type_="check")
        batch_op.alter_column(
            "session_type",
            existing_type=sa.Enum(
                "DIAGNOSTIC",
                "PRACTICE",
                "REVIEW",
                "REPAIR",
                "QUICK_CHECK",
                "EXAM",
                name="practice_session_type",
                native_enum=False,
            ),
            type_=sa.Enum(
                "DIAGNOSTIC",
                "PRACTICE",
                "REVIEW",
                "REPAIR",
                "QUICK_CHECK",
                "EXAM",
                "ROOT_CAUSE_VERIFICATION",
                name="practice_session_type",
                native_enum=False,
            ),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "practice_session_type",
            "session_type IN ('DIAGNOSTIC', 'PRACTICE', 'REVIEW', 'REPAIR', 'QUICK_CHECK', 'EXAM', 'ROOT_CAUSE_VERIFICATION')",
        )

    op.create_table(
        "root_cause_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "diagnosis_id",
            sa.Uuid(),
            sa.ForeignKey("root_cause_diagnoses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "practice_session_id",
            sa.Uuid(),
            sa.ForeignKey("practice_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                *verification_statuses,
                name="root_cause_verification_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "required_probe_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completed_probe_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "required_probe_count >= 0", name="required_probes_nonnegative"
        ),
        sa.CheckConstraint(
            "completed_probe_count >= 0", name="completed_probes_nonnegative"
        ),
    )
    op.create_index(
        "ix_root_cause_verification_diagnosis",
        "root_cause_verifications",
        ["diagnosis_id"],
    )
    op.create_index(
        "ix_root_cause_verification_practice_session",
        "root_cause_verifications",
        ["practice_session_id"],
    )
    op.create_index(
        "ix_root_cause_verification_diag_status",
        "root_cause_verifications",
        ["diagnosis_id", "status"],
    )

    op.create_table(
        "root_cause_verification_targets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "verification_id",
            sa.Uuid(),
            sa.ForeignKey("root_cause_verifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "root_cause_candidate_id",
            sa.Uuid(),
            sa.ForeignKey("root_cause_candidates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_type",
            sa.Enum(
                *target_types,
                name="root_cause_verification_target_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "target_concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "target_problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "misconception_definition_id",
            sa.Uuid(),
            sa.ForeignKey("misconception_definitions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "priority_order",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                *target_outcomes,
                name="root_cause_verification_outcome",
                native_enum=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("probe_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("average_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "priority_order >= 0", name="priority_order_nonnegative"
        ),
        sa.CheckConstraint("probe_count >= 0", name="probe_count_nonnegative"),
        sa.CheckConstraint("correct_count >= 0", name="correct_count_nonnegative"),
        sa.CheckConstraint(
            "average_score IS NULL OR (average_score >= 0 AND average_score <= 1)",
            name="target_average_score_range",
        ),
    )
    op.create_index(
        "ix_root_cause_verification_target_verification",
        "root_cause_verification_targets",
        ["verification_id"],
    )
    op.create_index(
        "ix_root_cause_verification_target_concept",
        "root_cause_verification_targets",
        ["target_concept_id"],
    )
    op.create_index(
        "ix_root_cause_verification_target_problem_type",
        "root_cause_verification_targets",
        ["target_problem_type_id"],
    )

    op.create_table(
        "root_cause_verification_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "verification_target_id",
            sa.Uuid(),
            sa.ForeignKey(
                "root_cause_verification_targets.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "order_index",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("desired_difficulty", sa.Float(), nullable=False),
        sa.Column("selection_score", sa.Float(), nullable=False),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("question_attempts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "order_index >= 0", name="item_order_index_nonnegative"
        ),
        sa.CheckConstraint(
            "desired_difficulty BETWEEN 0 AND 1", name="desired_difficulty_range"
        ),
    )
    op.create_index(
        "ix_root_cause_verification_item_target",
        "root_cause_verification_items",
        ["verification_target_id"],
    )
    op.create_index(
        "ix_root_cause_verification_item_question",
        "root_cause_verification_items",
        ["question_id"],
    )
    op.create_index(
        "ix_root_cause_verification_item_attempt",
        "root_cause_verification_items",
        ["attempt_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_root_cause_verification_item_attempt",
        table_name="root_cause_verification_items",
    )
    op.drop_index(
        "ix_root_cause_verification_item_question",
        table_name="root_cause_verification_items",
    )
    op.drop_index(
        "ix_root_cause_verification_item_target",
        table_name="root_cause_verification_items",
    )
    op.drop_table("root_cause_verification_items")

    op.drop_index(
        "ix_root_cause_verification_target_problem_type",
        table_name="root_cause_verification_targets",
    )
    op.drop_index(
        "ix_root_cause_verification_target_concept",
        table_name="root_cause_verification_targets",
    )
    op.drop_index(
        "ix_root_cause_verification_target_verification",
        table_name="root_cause_verification_targets",
    )
    op.drop_table("root_cause_verification_targets")

    op.drop_index(
        "ix_root_cause_verification_diag_status",
        table_name="root_cause_verifications",
    )
    op.drop_index(
        "ix_root_cause_verification_practice_session",
        table_name="root_cause_verifications",
    )
    op.drop_index(
        "ix_root_cause_verification_diagnosis",
        table_name="root_cause_verifications",
    )
    op.drop_table("root_cause_verifications")
    with op.batch_alter_table("practice_sessions") as batch_op:
        batch_op.drop_constraint("ck_practice_sessions_practice_session_type", type_="check")
        batch_op.alter_column(
            "session_type",
            existing_type=sa.Enum(
                "DIAGNOSTIC",
                "PRACTICE",
                "REVIEW",
                "REPAIR",
                "QUICK_CHECK",
                "EXAM",
                "ROOT_CAUSE_VERIFICATION",
                name="practice_session_type",
                native_enum=False,
            ),
            type_=sa.Enum(
                "DIAGNOSTIC",
                "PRACTICE",
                "REVIEW",
                "REPAIR",
                "QUICK_CHECK",
                "EXAM",
                name="practice_session_type",
                native_enum=False,
            ),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "practice_session_type",
            "session_type IN ('DIAGNOSTIC', 'PRACTICE', 'REVIEW', 'REPAIR', 'QUICK_CHECK', 'EXAM')",
        )
