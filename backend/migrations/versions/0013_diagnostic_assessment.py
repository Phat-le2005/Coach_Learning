"""Diagnostic assessment configuration and persisted blueprint.

Revision ID: 0013_diagnostic_assessment
Revises: 0012_question_content_hash
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0013_diagnostic_assessment"
down_revision: str | Sequence[str] | None = "0012_question_content_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("max_questions", sa.Integer(), nullable=False),
        sa.Column("minimum_problem_type_coverage", sa.Float(), nullable=False),
        sa.Column("confidence_threshold", sa.Float(), nullable=False),
        sa.Column("current_question_id", sa.Uuid(), nullable=True),
        sa.Column("current_target_problem_type_id", sa.Uuid(), nullable=True),
        sa.Column("current_target_concept_id", sa.Uuid(), nullable=True),
        sa.Column("current_difficulty", sa.Float(), nullable=True),
        sa.Column(
            "current_selection_reason",
            sa.Enum(
                "BLUEPRINT_COVERAGE",
                "CONFIDENCE_REFINEMENT",
                "PREREQUISITE_CHECK",
                name="diagnostic_selection_reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "completion_reason",
            sa.Enum(
                "CONFIDENCE_REACHED",
                "MAX_QUESTIONS",
                "NO_AVAILABLE_QUESTION",
                name="diagnostic_completion_reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "max_questions BETWEEN 1 AND 100",
            name=op.f("ck_diagnostic_assessments_max_questions_range"),
        ),
        sa.CheckConstraint(
            "minimum_problem_type_coverage > 0.0 "
            "AND minimum_problem_type_coverage <= 1.0",
            name=op.f("ck_diagnostic_assessments_minimum_coverage_range"),
        ),
        sa.CheckConstraint(
            "confidence_threshold BETWEEN 0.0 AND 1.0",
            name=op.f("ck_diagnostic_assessments_confidence_threshold_range"),
        ),
        sa.CheckConstraint(
            "current_difficulty IS NULL OR current_difficulty BETWEEN 0.0 AND 1.0",
            name=op.f("ck_diagnostic_assessments_current_difficulty_range"),
        ),
        sa.CheckConstraint(
            "(current_question_id IS NULL "
            "AND current_target_problem_type_id IS NULL "
            "AND current_target_concept_id IS NULL "
            "AND current_difficulty IS NULL "
            "AND current_selection_reason IS NULL) OR "
            "(current_question_id IS NOT NULL "
            "AND current_difficulty IS NOT NULL "
            "AND current_selection_reason IS NOT NULL "
            "AND ((current_target_problem_type_id IS NOT NULL "
            "AND current_target_concept_id IS NULL) "
            "OR (current_target_problem_type_id IS NULL "
            "AND current_target_concept_id IS NOT NULL)))",
            name=op.f("ck_diagnostic_assessments_pending_selection_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["practice_sessions.id"],
            name=op.f("fk_diagnostic_assessments_id_practice_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["current_question_id"],
            ["questions.id"],
            name=op.f("fk_diagnostic_assessments_current_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_target_problem_type_id"],
            ["problem_types.id"],
            name=op.f(
                "fk_diagnostic_assessments_current_target_problem_type_id_problem_types"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_target_concept_id"],
            ["concepts.id"],
            name=op.f("fk_diagnostic_assessments_current_target_concept_id_concepts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnostic_assessments")),
    )
    op.create_index(
        "ix_diagnostic_assessments_current_question_id",
        "diagnostic_assessments",
        ["current_question_id"],
        unique=False,
    )
    op.create_table(
        "diagnostic_blueprint_items",
        sa.Column("diagnostic_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type_id", sa.Uuid(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "order_index >= 0",
            name=op.f("ck_diagnostic_blueprint_items_order_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["diagnostic_assessment_id"],
            ["diagnostic_assessments.id"],
            name=op.f(
                "fk_diagnostic_blueprint_items_diagnostic_assessment_id_diagnostic_assessments"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            name=op.f("fk_diagnostic_blueprint_items_problem_type_id_problem_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "diagnostic_assessment_id",
            "problem_type_id",
            name=op.f("pk_diagnostic_blueprint_items"),
        ),
        sa.UniqueConstraint(
            "diagnostic_assessment_id",
            "order_index",
            name="uq_diagnostic_blueprint_items_assessment_order",
        ),
    )
    op.create_index(
        "ix_diagnostic_blueprint_items_problem_type_id",
        "diagnostic_blueprint_items",
        ["problem_type_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_diagnostic_blueprint_items_problem_type_id",
        table_name="diagnostic_blueprint_items",
    )
    op.drop_table("diagnostic_blueprint_items")
    op.drop_index(
        "ix_diagnostic_assessments_current_question_id",
        table_name="diagnostic_assessments",
    )
    op.drop_table("diagnostic_assessments")
