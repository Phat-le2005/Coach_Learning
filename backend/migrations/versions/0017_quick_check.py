"""Quick check sessions and question tracking.

Revision ID: 0017_quick_check
Revises: 0016_teacher_teaching_plans
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0017_quick_check"
down_revision: str | Sequence[str] | None = "0016_teacher_teaching_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quick_check_sessions",
        sa.Column(
            "id",
            sa.Uuid(),
            sa.ForeignKey("practice_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "teaching_plan_id",
            sa.Uuid(),
            sa.ForeignKey("teaching_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "classroom_id",
            sa.Uuid(),
            sa.ForeignKey("classrooms.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_quick_check_sessions_teaching_plan",
        "quick_check_sessions",
        ["teaching_plan_id"],
    )
    op.create_index(
        "ix_quick_check_sessions_classroom",
        "quick_check_sessions",
        ["classroom_id"],
    )

    op.create_table(
        "quick_check_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "quick_check_id",
            sa.Uuid(),
            sa.ForeignKey("quick_check_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "target_concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "target_role",
            sa.Enum(
                "UNDERSTANDING",
                "APPLICATION",
                "PREREQUISITE",
                name="quick_check_question_role",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "quick_check_id",
            "question_id",
            name="uq_quick_check_questions_quick_check_question",
        ),
        sa.UniqueConstraint(
            "quick_check_id",
            "order_index",
            name="uq_quick_check_questions_quick_check_order",
        ),
        sa.CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
    )
    op.create_index(
        "ix_quick_check_questions_quick_check_id",
        "quick_check_questions",
        ["quick_check_id"],
    )
    op.create_index(
        "ix_quick_check_questions_question_id",
        "quick_check_questions",
        ["question_id"],
    )


def downgrade() -> None:
    op.drop_table("quick_check_questions")
    op.drop_table("quick_check_sessions")
