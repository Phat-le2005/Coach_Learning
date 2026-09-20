"""Study planning core models: study plans and study tasks.

Revision ID: 0019_study_planning_core
Revises: 0018_spaced_review
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0019_study_planning_core"
down_revision: str | Sequence[str] | None = "0018_spaced_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Uuid(),
            sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "academic_goal_id",
            sa.Uuid(),
            sa.ForeignKey("academic_goals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "COMPLETED",
                "ARCHIVED",
                name="study_plan_status",
                native_enum=False,
            ),
            server_default="ACTIVE",
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
            "target_date IS NULL OR target_date >= start_date",
            name="ck_study_plans_target_date_after_start_date",
        ),
    )
    op.create_index(
        "ix_study_plans_academic_goal_id",
        "study_plans",
        ["academic_goal_id"],
    )
    op.create_index(
        "ix_study_plans_status",
        "study_plans",
        ["status"],
    )
    op.create_index(
        "ix_study_plans_student_id",
        "study_plans",
        ["student_id"],
    )
    op.create_index(
        "ix_study_plans_student_status",
        "study_plans",
        ["student_id", "status"],
    )

    op.create_table(
        "study_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "study_plan_id",
            sa.Uuid(),
            sa.ForeignKey("study_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_type",
            sa.Enum(
                "LEARN",
                "PRACTICE",
                "REPAIR",
                "REVIEW",
                "QUICK_CHECK",
                "MINI_TEST",
                "EXAM",
                name="study_task_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "IN_PROGRESS",
                "COMPLETED",
                "SKIPPED",
                name="study_task_status",
                native_enum=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column(
            "problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("subjects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="1", nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "estimated_duration_minutes > 0",
            name="ck_study_tasks_positive_duration",
        ),
        sa.CheckConstraint("priority > 0", name="ck_study_tasks_positive_priority"),
        sa.CheckConstraint("order_index >= 0", name="ck_study_tasks_nonnegative_order"),
    )
    op.create_index(
        "ix_study_tasks_concept_id",
        "study_tasks",
        ["concept_id"],
    )
    op.create_index(
        "ix_study_tasks_plan_date",
        "study_tasks",
        ["study_plan_id", "planned_date"],
    )
    op.create_index(
        "ix_study_tasks_plan_date_status",
        "study_tasks",
        ["study_plan_id", "planned_date", "status"],
    )
    op.create_index(
        "ix_study_tasks_planned_date",
        "study_tasks",
        ["planned_date"],
    )
    op.create_index(
        "ix_study_tasks_problem_type_id",
        "study_tasks",
        ["problem_type_id"],
    )
    op.create_index(
        "ix_study_tasks_status",
        "study_tasks",
        ["status"],
    )
    op.create_index(
        "ix_study_tasks_study_plan_id",
        "study_tasks",
        ["study_plan_id"],
    )
    op.create_index(
        "ix_study_tasks_subject_id",
        "study_tasks",
        ["subject_id"],
    )
    op.create_index(
        "ix_study_tasks_task_type",
        "study_tasks",
        ["task_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_study_tasks_task_type", table_name="study_tasks")
    op.drop_index("ix_study_tasks_subject_id", table_name="study_tasks")
    op.drop_index("ix_study_tasks_study_plan_id", table_name="study_tasks")
    op.drop_index("ix_study_tasks_status", table_name="study_tasks")
    op.drop_index("ix_study_tasks_problem_type_id", table_name="study_tasks")
    op.drop_index("ix_study_tasks_planned_date", table_name="study_tasks")
    op.drop_index("ix_study_tasks_plan_date_status", table_name="study_tasks")
    op.drop_index("ix_study_tasks_plan_date", table_name="study_tasks")
    op.drop_index("ix_study_tasks_concept_id", table_name="study_tasks")
    op.drop_table("study_tasks")

    op.drop_index("ix_study_plans_student_status", table_name="study_plans")
    op.drop_index("ix_study_plans_student_id", table_name="study_plans")
    op.drop_index("ix_study_plans_status", table_name="study_plans")
    op.drop_index("ix_study_plans_academic_goal_id", table_name="study_plans")
    op.drop_table("study_plans")
