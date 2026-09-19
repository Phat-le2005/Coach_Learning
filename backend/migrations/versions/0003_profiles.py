"""Role profiles and many-to-many parent/student relationships; backfill existing users.

Revision ID: 0003_profiles
Revises: 0002_auth_rbac
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_profiles"
down_revision: str | Sequence[str] | None = "0002_auth_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    students = op.create_table(
        "student_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("grade_level", sa.SmallInteger(), server_default="12", nullable=False),
        sa.Column("school_name", sa.String(200), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("grade_level BETWEEN 1 AND 12", name=op.f("ck_student_profiles_grade_level_range")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_student_profiles_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_student_profiles_user_id")),
    )
    teachers = op.create_table(
        "teacher_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("specialization", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_teacher_profiles_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teacher_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_teacher_profiles_user_id")),
    )
    parents = op.create_table(
        "parent_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_parent_profiles_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parent_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_parent_profiles_user_id")),
    )
    op.create_table(
        "parent_student_relationships",
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("length(trim(relationship_type)) > 0", name=op.f("ck_parent_student_relationships_relationship_type_not_blank")),
        sa.ForeignKeyConstraint(["parent_id"], ["parent_profiles.id"], name=op.f("fk_parent_student_relationships_parent_id_parent_profiles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"], name=op.f("fk_parent_student_relationships_student_id_student_profiles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("parent_id", "student_id", name=op.f("pk_parent_student_relationships")),
    )
    op.create_index(op.f("ix_parent_student_relationships_student_id"), "parent_student_relationships", ["student_id"])
    # PostgreSQL 13+ provides gen_random_uuid() without installing an extension.
    users = sa.Table(
        "users", sa.MetaData(), sa.Column("id", sa.Uuid()), sa.Column("role", sa.String(7))
    )
    for profiles, role in [(students, "STUDENT"), (teachers, "TEACHER"), (parents, "PARENT")]:
        op.execute(
            profiles.insert().from_select(
                ["id", "user_id"],
                sa.select(sa.func.gen_random_uuid(), users.c.id).where(users.c.role == role),
            )
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_parent_student_relationships_student_id"), table_name="parent_student_relationships")
    op.drop_table("parent_student_relationships")
    op.drop_table("parent_profiles")
    op.drop_table("teacher_profiles")
    op.drop_table("student_profiles")
