"""Classrooms with teacher assignments and student enrollments.

Revision ID: 0005_classrooms
Revises: 0004_academic_domain
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_classrooms"
down_revision: str | Sequence[str] | None = "0004_academic_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classrooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("academic_year", sa.String(20), nullable=False),
        sa.Column("grade_level", sa.SmallInteger(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_classrooms_name_not_blank")),
        sa.CheckConstraint(
            "length(trim(academic_year)) > 0", name=op.f("ck_classrooms_academic_year_not_blank")
        ),
        sa.CheckConstraint("grade_level BETWEEN 1 AND 12", name=op.f("ck_classrooms_grade_level_range")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_classrooms_created_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classrooms")),
    )
    op.create_index(op.f("ix_classrooms_created_by"), "classrooms", ["created_by"])
    op.create_table(
        "teacher_classrooms",
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.CheckConstraint("length(trim(role)) > 0", name=op.f("ck_teacher_classrooms_role_not_blank")),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teacher_profiles.id"],
            name=op.f("fk_teacher_classrooms_teacher_id_teacher_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_teacher_classrooms_classroom_id_classrooms"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("teacher_id", "classroom_id", name=op.f("pk_teacher_classrooms")),
    )
    op.create_index(
        op.f("ix_teacher_classrooms_classroom_id"), "teacher_classrooms", ["classroom_id"]
    )
    op.create_table(
        "student_enrollments",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                "COMPLETED",
                native_enum=False,
                create_constraint=True,
                name="enrollment_status",
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_enrollments_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_student_enrollments_classroom_id_classrooms"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("student_id", "classroom_id", name=op.f("pk_student_enrollments")),
    )
    op.create_index(
        op.f("ix_student_enrollments_classroom_status"),
        "student_enrollments",
        ["classroom_id", "status", "student_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_student_enrollments_classroom_status"), table_name="student_enrollments")
    op.drop_table("student_enrollments")
    op.drop_index(op.f("ix_teacher_classrooms_classroom_id"), table_name="teacher_classrooms")
    op.drop_table("teacher_classrooms")
    op.drop_index(op.f("ix_classrooms_created_by"), table_name="classrooms")
    op.drop_table("classrooms")
