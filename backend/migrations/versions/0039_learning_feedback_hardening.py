"""Harden post-repair learning feedback lifecycle with snapshot fields.

Revision ID: 0039_learning_feedback_hardening
Revises: 0038_learning_feedback_loop
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0039_learning_feedback_hardening"
down_revision: str | Sequence[str] | None = "0038_learning_feedback_loop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("learning_feedback_decisions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "next_target_type",
                sa.Enum(
                    "PROBLEM_TYPE",
                    "CONCEPT",
                    name="learning_feedback_next_target_type",
                    native_enum=False,
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "next_concept_id",
                sa.Uuid(),
                sa.ForeignKey("concepts.id", ondelete="RESTRICT", name="fk_learning_feedback_next_concept"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "next_problem_type_id",
                sa.Uuid(),
                sa.ForeignKey("problem_types.id", ondelete="RESTRICT", name="fk_learning_feedback_next_problem_type"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "next_reason_code",
                sa.Enum(
                    "VERIFIED_ROOT_CAUSE",
                    "CURRENT_LESSON",
                    "WEAK_PROBLEM_TYPE",
                    "PREREQUISITE_REPAIR",
                    "WEAK_CONCEPT",
                    "REVIEW_DUE",
                    "DIFFICULTY_PROGRESSION",
                    "DIAGNOSTIC_FOLLOWUP",
                    name="learning_feedback_next_reason_code",
                    native_enum=False,
                ),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_feedback_decisions") as batch_op:
        batch_op.drop_column("next_reason_code")
        batch_op.drop_column("next_problem_type_id")
        batch_op.drop_column("next_concept_id")
        batch_op.drop_column("next_target_type")
