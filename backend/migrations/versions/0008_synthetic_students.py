"""Synthetic student profiles, study sessions, and attempt facts.

Revision ID: 0008_synthetic_students
Revises: 0007_question_import
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_synthetic_students"
down_revision: str | Sequence[str] | None = "0007_question_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("is_synthetic", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "synthetic_profile",
                sa.Enum(
                    "STRONG",
                    "AVERAGE",
                    "WEAK",
                    "SPECIFIC_GAP",
                    "INCONSISTENT",
                    native_enum=False,
                    create_constraint=False,
                    name="synthetic_student_profile",
                ),
                nullable=True,
            )
        )

    # Constraints are intentionally created in a second batch. PostgreSQL may
    # emit type-bound enum checks before ADD COLUMN when both share one batch.
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.create_check_constraint(
            "synthetic_student_profile",
            "synthetic_profile IN ('STRONG', 'AVERAGE', 'WEAK', "
            "'SPECIFIC_GAP', 'INCONSISTENT')",
        )
        batch_op.create_check_constraint(
            "synthetic_profile_consistency",
            "(is_synthetic AND synthetic_profile IS NOT NULL) OR "
            "(NOT is_synthetic AND synthetic_profile IS NULL)",
        )

    op.create_table(
        "study_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "ended_at > started_at", name=op.f("ck_study_sessions_time_range")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_study_sessions_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_sessions")),
    )
    op.create_index(
        "ix_study_sessions_student_started",
        "study_sessions",
        ["student_id", "started_at"],
    )

    op.create_table(
        "student_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=True),
        sa.Column("study_session_id", sa.Uuid(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "response_time_ms > 0", name=op.f("ck_student_attempts_response_time_positive")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_attempts_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_student_attempts_concept_id_concepts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_student_attempts_question_id_questions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["study_session_id"],
            ["study_sessions.id"],
            name=op.f("fk_student_attempts_study_session_id_study_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_attempts")),
    )
    op.create_index(
        "ix_student_attempts_student_time",
        "student_attempts",
        ["student_id", "attempted_at"],
    )
    op.create_index(
        "ix_student_attempts_concept_student",
        "student_attempts",
        ["concept_id", "student_id"],
    )
    op.create_index(
        "ix_student_attempts_synthetic_time",
        "student_attempts",
        ["is_synthetic", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_attempts_synthetic_time", table_name="student_attempts")
    op.drop_index("ix_student_attempts_concept_student", table_name="student_attempts")
    op.drop_index("ix_student_attempts_student_time", table_name="student_attempts")
    op.drop_table("student_attempts")
    op.drop_index("ix_study_sessions_student_started", table_name="study_sessions")
    op.drop_table("study_sessions")
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_student_profiles_synthetic_profile_consistency"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_student_profiles_synthetic_student_profile"), type_="check"
        )
        batch_op.drop_column("synthetic_profile")
        batch_op.drop_column("is_synthetic")
