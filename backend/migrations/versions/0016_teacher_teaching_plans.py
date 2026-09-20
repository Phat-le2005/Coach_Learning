"""Teacher teaching plans and plan items.

Revision ID: 0016_teacher_teaching_plans
Revises: 0015_diagnostic_attempt_context
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0016_teacher_teaching_plans"
down_revision: str | Sequence[str] | None = "0015_diagnostic_attempt_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teaching_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "classroom_id",
            sa.Uuid(),
            sa.ForeignKey("classrooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("target_end_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PLANNED",
                "ACTIVE",
                "COMPLETED",
                "CANCELLED",
                name="teaching_plan_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="PLANNED",
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_end_date IS NULL OR target_end_date >= start_date",
            name="target_end_date_after_start_date",
        ),
    )
    op.create_index("ix_teaching_plans_classroom_id", "teaching_plans", ["classroom_id"])
    op.create_index("ix_teaching_plans_subject_id", "teaching_plans", ["subject_id"])
    op.create_index("ix_teaching_plans_status", "teaching_plans", ["status"])
    op.create_index("ix_teaching_plans_created_by", "teaching_plans", ["created_by"])
    op.create_index(
        "ix_teaching_plans_classroom_subject_status",
        "teaching_plans",
        ["classroom_id", "subject_id", "status"],
    )

    op.create_table(
        "teaching_plan_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "teaching_plan_id",
            sa.Uuid(),
            sa.ForeignKey("teaching_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "learning_outcome_id",
            sa.Uuid(),
            sa.ForeignKey("learning_outcomes.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "teaching_plan_id",
            "problem_type_id",
            name="uq_teaching_plan_items_plan_problem_type",
        ),
        sa.CheckConstraint("priority > 0", name="priority_positive"),
        sa.CheckConstraint(
            "order_index IS NULL OR order_index >= 0", name="order_index_nonnegative"
        ),
    )
    op.create_index(
        "ix_teaching_plan_items_teaching_plan_id", "teaching_plan_items", ["teaching_plan_id"]
    )
    op.create_index(
        "ix_teaching_plan_items_problem_type_id", "teaching_plan_items", ["problem_type_id"]
    )
    op.create_index(
        "ix_teaching_plan_items_learning_outcome_id",
        "teaching_plan_items",
        ["learning_outcome_id"],
    )
    op.create_index(
        "ix_teaching_plan_items_plan_priority",
        "teaching_plan_items",
        ["teaching_plan_id", "priority"],
    )


def downgrade() -> None:
    op.drop_table("teaching_plan_items")
    op.drop_table("teaching_plans")
