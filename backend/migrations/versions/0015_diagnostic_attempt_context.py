"""Diagnostic attempt context tracking target and reason per attempt.

Revision ID: 0015_diagnostic_attempt_context
Revises: 0014_student_academic_goals
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0015_diagnostic_attempt_context"
down_revision: str | Sequence[str] | None = "0014_student_academic_goals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_attempt_contexts",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("target_problem_type_id", sa.Uuid(), nullable=True),
        sa.Column("target_concept_id", sa.Uuid(), nullable=True),
        sa.Column(
            "selection_reason",
            sa.Enum(
                "BLUEPRINT_COVERAGE",
                "CONFIDENCE_REFINEMENT",
                "PREREQUISITE_CHECK",
                name="diagnostic_selection_reason",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("desired_difficulty", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(target_problem_type_id IS NOT NULL AND target_concept_id IS NULL) OR "
            "(target_problem_type_id IS NULL AND target_concept_id IS NOT NULL)",
            name=op.f("ck_diagnostic_attempt_contexts_target_exclusive"),
        ),
        sa.CheckConstraint(
            "desired_difficulty BETWEEN 0.0 AND 1.0",
            name=op.f("ck_diagnostic_attempt_contexts_desired_difficulty_range"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["question_attempts.id"],
            name=op.f("fk_diagnostic_attempt_contexts_attempt_id_question_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_problem_type_id"],
            ["problem_types.id"],
            name=op.f("fk_diagnostic_attempt_contexts_target_problem_type_id_problem_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_concept_id"],
            ["concepts.id"],
            name=op.f("fk_diagnostic_attempt_contexts_target_concept_id_concepts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_diagnostic_attempt_contexts")),
    )
    op.create_index(
        "ix_diagnostic_attempt_contexts_target_pt",
        "diagnostic_attempt_contexts",
        ["target_problem_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_diagnostic_attempt_contexts_target_concept",
        "diagnostic_attempt_contexts",
        ["target_concept_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_diagnostic_attempt_contexts_target_concept",
        table_name="diagnostic_attempt_contexts",
    )
    op.drop_index(
        "ix_diagnostic_attempt_contexts_target_pt",
        table_name="diagnostic_attempt_contexts",
    )
    op.drop_table("diagnostic_attempt_contexts")
