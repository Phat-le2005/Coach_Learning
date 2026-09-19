"""Concept and problem-type mastery source-of-truth tables.

Revision ID: 0011_mastery_engine
Revises: 0010_practice_engine
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_mastery_engine"
down_revision: str | Sequence[str] | None = "0010_practice_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_concept_mastery",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mastery_score BETWEEN 0.0 AND 1.0",
            name=op.f("ck_student_concept_mastery_mastery_score_range"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name=op.f("ck_student_concept_mastery_confidence_range"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_student_concept_mastery_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "correct_count >= 0",
            name=op.f("ck_student_concept_mastery_correct_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "correct_count <= attempt_count",
            name=op.f("ck_student_concept_mastery_correct_not_above_attempts"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_concept_mastery_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_student_concept_mastery_concept_id_concepts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "student_id", "concept_id", name=op.f("pk_student_concept_mastery")
        ),
    )
    op.create_index(
        "ix_student_concept_mastery_concept_student",
        "student_concept_mastery",
        ["concept_id", "student_id"],
    )

    op.create_table(
        "student_problem_type_mastery",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type_id", sa.Uuid(), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mastery_score BETWEEN 0.0 AND 1.0",
            name=op.f("ck_student_problem_type_mastery_mastery_score_range"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name=op.f("ck_student_problem_type_mastery_confidence_range"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_student_problem_type_mastery_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "correct_count >= 0",
            name=op.f("ck_student_problem_type_mastery_correct_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "correct_count <= attempt_count",
            name=op.f("ck_student_problem_type_mastery_correct_not_above_attempts"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_problem_type_mastery_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            name=op.f("fk_student_problem_type_mastery_problem_type_id_problem_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "student_id",
            "problem_type_id",
            name=op.f("pk_student_problem_type_mastery"),
        ),
    )
    op.create_index(
        "ix_student_problem_type_mastery_problem_student",
        "student_problem_type_mastery",
        ["problem_type_id", "student_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_problem_type_mastery_problem_student",
        table_name="student_problem_type_mastery",
    )
    op.drop_table("student_problem_type_mastery")
    op.drop_index(
        "ix_student_concept_mastery_concept_student",
        table_name="student_concept_mastery",
    )
    op.drop_table("student_concept_mastery")

