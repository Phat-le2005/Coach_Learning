"""Spaced review schedules for problem types and concepts.

Revision ID: 0018_spaced_review
Revises: 0017_quick_check
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0018_spaced_review"
down_revision: str | Sequence[str] | None = "0017_quick_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Uuid(),
            sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "next_review_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "review_interval_days",
            sa.Float(),
            server_default="1.0",
            nullable=False,
        ),
        sa.Column(
            "review_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "last_review_result",
            sa.String(length=50),
            nullable=True,
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
            "((problem_type_id IS NOT NULL AND concept_id IS NULL) OR "
            "(problem_type_id IS NULL AND concept_id IS NOT NULL))",
            name="chk_review_schedule_single_target",
        ),
        sa.CheckConstraint(
            "review_interval_days > 0",
            name="chk_review_schedule_positive_interval",
        ),
        sa.CheckConstraint(
            "review_count >= 0",
            name="chk_review_schedule_nonnegative_count",
        ),
    )

    op.create_index(
        "ix_review_schedules_student_next",
        "review_schedules",
        ["student_id", "next_review_at"],
    )
    op.create_index(
        "ix_review_schedules_problem_type_id",
        "review_schedules",
        ["problem_type_id"],
    )
    op.create_index(
        "ix_review_schedules_concept_id",
        "review_schedules",
        ["concept_id"],
    )
    op.create_index(
        "uq_review_schedules_student_pt",
        "review_schedules",
        ["student_id", "problem_type_id"],
        unique=True,
        postgresql_where=sa.text("problem_type_id IS NOT NULL"),
        sqlite_where=sa.text("problem_type_id IS NOT NULL"),
    )
    op.create_index(
        "uq_review_schedules_student_concept",
        "review_schedules",
        ["student_id", "concept_id"],
        unique=True,
        postgresql_where=sa.text("concept_id IS NOT NULL"),
        sqlite_where=sa.text("concept_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_review_schedules_student_concept",
        table_name="review_schedules",
        postgresql_where=sa.text("concept_id IS NOT NULL"),
        sqlite_where=sa.text("concept_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_review_schedules_student_pt",
        table_name="review_schedules",
        postgresql_where=sa.text("problem_type_id IS NOT NULL"),
        sqlite_where=sa.text("problem_type_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_review_schedules_concept_id",
        table_name="review_schedules",
    )
    op.drop_index(
        "ix_review_schedules_problem_type_id",
        table_name="review_schedules",
    )
    op.drop_index(
        "ix_review_schedules_student_next",
        table_name="review_schedules",
    )
    op.drop_table("review_schedules")
