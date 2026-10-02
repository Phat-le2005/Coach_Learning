"""Persist evidence-driven root-cause hypotheses and ranked candidates.

Revision ID: 0034_root_cause_diagnostics
Revises: 0033_material_assignment_snapshot
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0034_root_cause_diagnostics"
down_revision: str | Sequence[str] | None = "0033_material_assignment_snapshot"
branch_labels = None
depends_on = None


diagnosis_types = (
    "PREREQUISITE_CONCEPT_GAP",
    "DIRECT_CONCEPT_GAP",
    "PROBLEM_TYPE_PROCEDURE_GAP",
    "MISCONCEPTION_HYPOTHESIS",
    "MULTI_FACTOR_GAP",
    "INSUFFICIENT_EVIDENCE",
)


def upgrade() -> None:
    op.create_table(
        "root_cause_diagnoses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "learning_evidence_event_id",
            sa.Uuid(),
            sa.ForeignKey("learning_evidence_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Uuid(),
            sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "classroom_id",
            sa.Uuid(),
            sa.ForeignKey("classrooms.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "assignment_id",
            sa.Uuid(),
            sa.ForeignKey("assignments.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "target_problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "diagnosis_type",
            sa.Enum(*diagnosis_types, name="root_cause_diagnosis_type", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "HYPOTHESIS",
                "STRONG_HYPOTHESIS",
                "INSUFFICIENT_EVIDENCE",
                name="root_cause_diagnosis_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "root_concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "misconception_definition_id",
            sa.Uuid(),
            sa.ForeignKey("misconception_definitions.id", ondelete="RESTRICT"),
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("supporting_evidence_count", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "learning_evidence_event_id", name="uq_root_cause_diagnosis_evidence"
        ),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        sa.CheckConstraint(
            "supporting_evidence_count >= 0", name="supporting_count_nonnegative"
        ),
    )
    op.create_index(
        "ix_root_cause_student_created",
        "root_cause_diagnoses",
        ["student_id", "created_at"],
    )
    op.create_index(
        "ix_root_cause_subject_type",
        "root_cause_diagnoses",
        ["subject_id", "diagnosis_type"],
    )

    op.create_table(
        "root_cause_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "diagnosis_id",
            sa.Uuid(),
            sa.ForeignKey("root_cause_diagnoses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "candidate_type",
            sa.Enum(*diagnosis_types, name="root_cause_candidate_type", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            sa.Uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "problem_type_id",
            sa.Uuid(),
            sa.ForeignKey("problem_types.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "misconception_definition_id",
            sa.Uuid(),
            sa.ForeignKey("misconception_definitions.id", ondelete="RESTRICT"),
        ),
        sa.Column("graph_distance", sa.Integer()),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("mastery_deficit_signal", sa.Float(), nullable=False),
        sa.Column("recent_error_signal", sa.Float(), nullable=False),
        sa.Column("structural_signal", sa.Float(), nullable=False),
        sa.Column("misconception_signal", sa.Float(), nullable=False),
        sa.Column("evidence_volume_signal", sa.Float(), nullable=False),
        sa.Column("supporting_event_count", sa.Integer(), nullable=False),
        sa.Column("conflicting_event_count", sa.Integer(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "diagnosis_id", "rank", name="uq_root_cause_candidate_rank"
        ),
        sa.CheckConstraint("rank > 0", name="rank_positive"),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        sa.CheckConstraint(
            "graph_distance IS NULL OR graph_distance >= 0",
            name="graph_distance_nonnegative",
        ),
        sa.CheckConstraint(
            "supporting_event_count >= 0 AND conflicting_event_count >= 0",
            name="event_counts_nonnegative",
        ),
    )
    op.create_index(
        "ix_root_cause_candidates_concept", "root_cause_candidates", ["concept_id"]
    )
    op.create_index(
        "ix_root_cause_candidates_problem_type",
        "root_cause_candidates",
        ["problem_type_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_root_cause_candidates_problem_type", table_name="root_cause_candidates"
    )
    op.drop_index(
        "ix_root_cause_candidates_concept", table_name="root_cause_candidates"
    )
    op.drop_table("root_cause_candidates")
    op.drop_index("ix_root_cause_subject_type", table_name="root_cause_diagnoses")
    op.drop_index("ix_root_cause_student_created", table_name="root_cause_diagnoses")
    op.drop_table("root_cause_diagnoses")
