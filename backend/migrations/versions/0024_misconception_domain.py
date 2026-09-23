"""Add misconception taxonomy and student misconception state.

Revision ID: 0024_misconception_domain
Revises: 0023_hint_system
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0024_misconception_domain"
down_revision: str | Sequence[str] | None = "0023_hint_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "misconception_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "CONCEPTUAL",
                "PROCEDURAL",
                "CALCULATION",
                "READING",
                "CARELESS",
                "OTHER",
                name="misconception_category",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "code = upper(trim(code)) AND length(code) > 0",
            name=op.f("ck_misconception_definitions_code_normalized"),
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name=op.f("ck_misconception_definitions_name_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(description)) > 0",
            name=op.f("ck_misconception_definitions_description_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_misconception_definitions_concept_id_concepts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            name=op.f(
                "fk_misconception_definitions_problem_type_id_problem_types"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_misconception_definitions")),
        sa.UniqueConstraint(
            "code", name=op.f("uq_misconception_definitions_code")
        ),
    )
    op.create_index(
        "ix_misconception_definitions_concept_active",
        "misconception_definitions",
        ["concept_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_misconception_definitions_problem_type_id",
        "misconception_definitions",
        ["problem_type_id"],
        unique=False,
    )

    op.create_table(
        "student_misconceptions",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("misconception_definition_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SUSPECTED",
                "CONFIRMED",
                "RESOLVED",
                name="student_misconception_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="SUSPECTED",
            nullable=False,
        ),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name=op.f("ck_student_misconceptions_confidence_range"),
        ),
        sa.CheckConstraint(
            "occurrence_count > 0",
            name=op.f("ck_student_misconceptions_occurrence_count_positive"),
        ),
        sa.CheckConstraint(
            "first_detected_at <= last_detected_at",
            name=op.f("ck_student_misconceptions_detection_time_order"),
        ),
        sa.CheckConstraint(
            "(status = 'RESOLVED' AND resolved_at IS NOT NULL) OR "
            "(status IN ('SUSPECTED', 'CONFIRMED') AND resolved_at IS NULL)",
            name=op.f(
                "ck_student_misconceptions_status_resolved_at_consistency"
            ),
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= last_detected_at",
            name=op.f("ck_student_misconceptions_resolved_after_detection"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_misconceptions_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["misconception_definition_id"],
            ["misconception_definitions.id"],
            name=op.f(
                "fk_student_misconceptions_misconception_definition_id_misconception_definitions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "student_id",
            "misconception_definition_id",
            name=op.f("pk_student_misconceptions"),
        ),
    )
    op.create_index(
        "ix_student_misconceptions_student_status_confidence",
        "student_misconceptions",
        ["student_id", "status", "confidence"],
        unique=False,
    )
    op.create_index(
        "ix_student_misconceptions_definition_status",
        "student_misconceptions",
        ["misconception_definition_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_misconceptions_definition_status",
        table_name="student_misconceptions",
    )
    op.drop_index(
        "ix_student_misconceptions_student_status_confidence",
        table_name="student_misconceptions",
    )
    op.drop_table("student_misconceptions")
    op.drop_index(
        "ix_misconception_definitions_problem_type_id",
        table_name="misconception_definitions",
    )
    op.drop_index(
        "ix_misconception_definitions_concept_active",
        table_name="misconception_definitions",
    )
    op.drop_table("misconception_definitions")
