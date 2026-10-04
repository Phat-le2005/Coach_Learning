"""Add question bank sufficiency and supply gap tracking tables.

Revision ID: 0040_question_supply_gap
Revises: 0039_learning_feedback_hardening
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0040_question_supply_gap"
down_revision: str | Sequence[str] | None = "0039_learning_feedback_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_supply_gaps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "use_case",
            sa.Enum(
                "ROOT_CAUSE_VERIFICATION",
                "ADAPTIVE_REPAIR",
                "REVIEW",
                "CURRENT_LEARNING",
                name="question_supply_use_case",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sa.Enum(
                "CONCEPT",
                "PROBLEM_TYPE",
                "MISCONCEPTION",
                name="question_supply_target_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "misconception_definition_id",
            sa.Uuid(),
            sa.ForeignKey("misconception_definitions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("desired_difficulty", sa.Float(), nullable=True),
        sa.Column("difficulty_min", sa.Float(), nullable=False),
        sa.Column("difficulty_max", sa.Float(), nullable=False),
        sa.Column("minimum_required_count", sa.Integer(), nullable=False),
        sa.Column("preferred_count", sa.Integer(), nullable=False),
        sa.Column(
            "approved_eligible_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "approved_in_band_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "pipeline_candidate_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="question_supply_severity",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "IN_PROGRESS",
                "RESOLVED",
                "DISMISSED",
                name="question_supply_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column(
            "demand_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "first_observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_assessed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("signature", name="uq_question_supply_gap_signature"),
        sa.CheckConstraint(
            "desired_difficulty IS NULL OR (desired_difficulty >= 0.0 AND desired_difficulty <= 1.0)",
            name="ck_supply_gaps_desired_difficulty",
        ),
        sa.CheckConstraint(
            "difficulty_min >= 0.0 AND difficulty_min <= difficulty_max AND difficulty_max <= 1.0",
            name="ck_supply_gaps_difficulty_range",
        ),
        sa.CheckConstraint(
            "minimum_required_count > 0 AND preferred_count >= minimum_required_count",
            name="ck_supply_gaps_counts_logic",
        ),
        sa.CheckConstraint(
            "approved_eligible_count >= 0 AND approved_in_band_count >= 0 AND approved_in_band_count <= approved_eligible_count",
            name="ck_supply_gaps_approved_counts",
        ),
        sa.CheckConstraint(
            "pipeline_candidate_count >= 0 AND demand_count >= 0",
            name="ck_supply_gaps_pipeline_demand",
        ),
    )

    op.create_index(
        "ix_supply_gaps_status_severity",
        "question_supply_gaps",
        ["status", "severity"],
    )
    op.create_index(
        "ix_supply_gaps_subject_status",
        "question_supply_gaps",
        ["subject_id", "status"],
    )
    op.create_index(
        "ix_supply_gaps_use_case_status",
        "question_supply_gaps",
        ["use_case", "status"],
    )
    op.create_index(
        "ix_supply_gaps_concept_id",
        "question_supply_gaps",
        ["concept_id"],
    )
    op.create_index(
        "ix_supply_gaps_problem_type_id",
        "question_supply_gaps",
        ["problem_type_id"],
    )
    op.create_index(
        "ix_supply_gaps_misconception_id",
        "question_supply_gaps",
        ["misconception_definition_id"],
    )

    op.create_table(
        "question_supply_gap_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "gap_id",
            sa.Uuid(),
            sa.ForeignKey("question_supply_gaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Uuid(),
            sa.ForeignKey("student_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_kind",
            sa.Enum(
                "LEARNING_FEEDBACK",
                "ROOT_CAUSE_VERIFICATION",
                "ADAPTIVE_REPAIR_START",
                "ADAPTIVE_REPAIR_RUNTIME",
                "MANUAL_ASSESSMENT",
                name="question_supply_obs_source_kind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("source_entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "reason_code",
            sa.Enum(
                "NO_APPROVED_TARGET_QUESTIONS",
                "INSUFFICIENT_APPROVED_TARGET_COUNT",
                "INSUFFICIENT_DIFFICULTY_COVERAGE",
                "NO_AUTO_EVALUABLE_TARGET_QUESTIONS",
                "STUDENT_EXPOSURE_EXHAUSTED",
                name="question_supply_obs_reason_code",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("observed_approved_eligible_count", sa.Integer(), nullable=False),
        sa.Column("observed_approved_in_band_count", sa.Integer(), nullable=False),
        sa.Column("observed_fresh_eligible_count", sa.Integer(), nullable=True),
        sa.Column("observed_fresh_in_band_count", sa.Integer(), nullable=True),
        sa.Column("observed_excluded_exposure_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "gap_id",
            "source_kind",
            "source_entity_id",
            name="uq_supply_gap_observation_source",
        ),
    )

    op.create_index(
        "ix_supply_gap_obs_gap_created",
        "question_supply_gap_observations",
        ["gap_id", "created_at"],
    )
    op.create_index(
        "ix_supply_gap_obs_student_created",
        "question_supply_gap_observations",
        ["student_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_supply_gap_obs_student_created",
        table_name="question_supply_gap_observations",
    )
    op.drop_index(
        "ix_supply_gap_obs_gap_created",
        table_name="question_supply_gap_observations",
    )
    op.drop_table("question_supply_gap_observations")

    op.drop_index("ix_supply_gaps_misconception_id", table_name="question_supply_gaps")
    op.drop_index("ix_supply_gaps_problem_type_id", table_name="question_supply_gaps")
    op.drop_index("ix_supply_gaps_concept_id", table_name="question_supply_gaps")
    op.drop_index("ix_supply_gaps_use_case_status", table_name="question_supply_gaps")
    op.drop_index("ix_supply_gaps_subject_status", table_name="question_supply_gaps")
    op.drop_index("ix_supply_gaps_status_severity", table_name="question_supply_gaps")
    op.drop_table("question_supply_gaps")
