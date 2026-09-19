"""Student academic goals and subject goals.

Revision ID: 0014_student_academic_goals
Revises: 0013_diagnostic_assessment
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0014_student_academic_goals"
down_revision: str | Sequence[str] | None = "0013_diagnostic_assessment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "academic_goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("target_exam", sa.String(length=100), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column("available_daily_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "COMPLETED",
                "ABANDONED",
                "ARCHIVED",
                name="academic_goal_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("target_university", sa.String(length=200), nullable=True),
        sa.Column("target_major", sa.String(length=200), nullable=True),
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
            "available_daily_minutes > 0 AND available_daily_minutes <= 1440",
            name=op.f("ck_academic_goals_daily_minutes"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_academic_goals_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_academic_goals")),
    )
    op.create_index(
        "ix_academic_goals_student_id",
        "academic_goals",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        "ix_academic_goals_status",
        "academic_goals",
        ["status"],
        unique=False,
    )

    op.create_table(
        "subject_goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("academic_goal_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("current_score", sa.Float(), nullable=True),
        sa.Column("target_score", sa.Float(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=True),
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
            "current_score IS NULL OR current_score >= 0.0",
            name=op.f("ck_subject_goals_current_score_non_negative"),
        ),
        sa.CheckConstraint(
            "target_score >= 0.0",
            name=op.f("ck_subject_goals_target_score_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["academic_goal_id"],
            ["academic_goals.id"],
            name=op.f("fk_subject_goals_academic_goal_id_academic_goals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_subject_goals_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject_goals")),
        sa.UniqueConstraint(
            "academic_goal_id",
            "subject_id",
            name=op.f("uq_subject_goals_academic_goal_subject"),
        ),
    )
    op.create_index(
        "ix_subject_goals_academic_goal_id",
        "subject_goals",
        ["academic_goal_id"],
        unique=False,
    )
    op.create_index(
        "ix_subject_goals_subject_id",
        "subject_goals",
        ["subject_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subject_goals_subject_id",
        table_name="subject_goals",
    )
    op.drop_index(
        "ix_subject_goals_academic_goal_id",
        table_name="subject_goals",
    )
    op.drop_table("subject_goals")
    op.drop_index(
        "ix_academic_goals_status",
        table_name="academic_goals",
    )
    op.drop_index(
        "ix_academic_goals_student_id",
        table_name="academic_goals",
    )
    op.drop_table("academic_goals")
