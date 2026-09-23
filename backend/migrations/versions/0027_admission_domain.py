"""Add admission domain tables.

Revision ID: 0027_admission_domain
Revises: 0026_exam_simulator
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0027_admission_domain"
down_revision: str | Sequence[str] | None = "0026_exam_simulator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. universities
    op.create_table(
        "universities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("length(trim(code)) > 0", name=op.f("ck_universities_code_not_blank")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_universities_name_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_universities")),
        sa.UniqueConstraint("code", name=op.f("uq_universities_code")),
    )
    op.create_index(
        op.f("ix_universities_code"),
        "universities",
        ["code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_universities_region"),
        "universities",
        ["region"],
        unique=False,
    )

    # 2. majors
    op.create_table(
        "majors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("length(trim(code)) > 0", name=op.f("ck_majors_code_not_blank")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_majors_name_not_blank")),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.id"],
            name=op.f("fk_majors_university_id_universities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_majors")),
        sa.UniqueConstraint("university_id", "code", name=op.f("uq_majors_university_code")),
    )
    op.create_index(
        op.f("ix_majors_university_code"),
        "majors",
        ["university_id", "code"],
        unique=False,
    )

    # 3. admission_methods
    op.create_table(
        "admission_methods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("length(trim(code)) > 0", name=op.f("ck_admission_methods_code_not_blank")),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_admission_methods_name_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admission_methods")),
        sa.UniqueConstraint("code", name=op.f("uq_admission_methods_code")),
    )
    op.create_index(
        op.f("ix_admission_methods_code"),
        "admission_methods",
        ["code"],
        unique=True,
    )

    # 4. admission_data_sources
    op.create_table(
        "admission_data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("source_type", sa.String(length=100), server_default="OFFICIAL_PORTAL", nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("publisher", sa.String(length=300), nullable=True),
        sa.Column("published_year", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_admission_data_sources_name_not_blank")),
        sa.CheckConstraint("published_year >= 2000", name=op.f("ck_admission_data_sources_published_year_valid")),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.id"],
            name=op.f("fk_admission_data_sources_verified_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admission_data_sources")),
    )
    op.create_index(
        op.f("ix_admission_data_sources_year"),
        "admission_data_sources",
        ["published_year"],
        unique=False,
    )

    # 5. admission_rules
    op.create_table(
        "admission_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("major_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("method_id", sa.Uuid(), nullable=False),
        sa.Column("subject_combination", sa.String(length=100), nullable=False),
        sa.Column("requirements", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("quota", sa.Integer(), nullable=True),
        sa.Column("historical_score", sa.Float(), nullable=True),
        sa.Column("source_reference", sa.String(length=1000), nullable=True),
        sa.Column("data_source_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("year >= 2000", name=op.f("ck_admission_rules_year_valid")),
        sa.CheckConstraint("quota IS NULL OR quota >= 0", name=op.f("ck_admission_rules_quota_nonnegative")),
        sa.CheckConstraint("historical_score IS NULL OR historical_score >= 0.0", name=op.f("ck_admission_rules_historical_score_nonnegative")),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["admission_data_sources.id"],
            name=op.f("fk_admission_rules_data_source_id_admission_data_sources"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["major_id"],
            ["majors.id"],
            name=op.f("fk_admission_rules_major_id_majors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["method_id"],
            ["admission_methods.id"],
            name=op.f("fk_admission_rules_method_id_admission_methods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.id"],
            name=op.f("fk_admission_rules_university_id_universities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.id"],
            name=op.f("fk_admission_rules_verified_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admission_rules")),
        sa.UniqueConstraint(
            "major_id", "year", "method_id", "subject_combination",
            name=op.f("uq_admission_rules_major_year_method_combination"),
        ),
    )
    op.create_index(
        op.f("ix_admission_rules_major_year"),
        "admission_rules",
        ["major_id", "year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admission_rules_university_year"),
        "admission_rules",
        ["university_id", "year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admission_rules_year_method"),
        "admission_rules",
        ["year", "method_id"],
        unique=False,
    )

    # 6. student_admission_targets
    op.create_table(
        "student_admission_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("major_id", sa.Uuid(), nullable=False),
        sa.Column(
            "target_type",
            sa.Enum(
                "DREAM",
                "TARGET",
                "SAFE",
                name="admission_target_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("target_year", sa.Integer(), server_default="2026", nullable=False),
        sa.Column("priority_order", sa.Integer(), server_default="1", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("priority_order >= 1", name=op.f("ck_student_admission_targets_priority_order_positive")),
        sa.CheckConstraint("target_year >= 2020", name=op.f("ck_student_admission_targets_target_year_valid")),
        sa.ForeignKeyConstraint(
            ["major_id"],
            ["majors.id"],
            name=op.f("fk_student_admission_targets_major_id_majors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_admission_targets_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.id"],
            name=op.f("fk_student_admission_targets_university_id_universities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_admission_targets")),
        sa.UniqueConstraint(
            "student_id", "university_id", "major_id", "target_year",
            name=op.f("uq_student_admission_targets_student_major_year"),
        ),
    )
    op.create_index(
        op.f("ix_student_admission_targets_student_year"),
        "student_admission_targets",
        ["student_id", "target_year"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("student_admission_targets")
    op.drop_table("admission_rules")
    op.drop_table("admission_data_sources")
    op.drop_table("admission_methods")
    op.drop_table("majors")
    op.drop_table("universities")
