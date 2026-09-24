"""Add four-statement true/false question groups.

Revision ID: 0030_question_groups
Revises: 0029_tutor_learning_memory
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0030_question_groups"
down_revision: str | Sequence[str] | None = "0029_tutor_learning_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "group_type",
            sa.Enum(
                "TRUE_FALSE_FOUR",
                name="question_group_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "scoring_policy",
            sa.Enum(
                "MOET_2025_TRUE_FALSE",
                name="question_group_scoring_policy",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("difficulty", sa.Float(), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("source_year", sa.Integer(), nullable=True),
        sa.Column(
            "cognitive_level",
            sa.Enum(
                "REMEMBER",
                "UNDERSTAND",
                "APPLY",
                "ANALYZE",
                name="question_group_cognitive_level",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("exam_weight", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "REVIEW",
                "APPROVED",
                "ARCHIVED",
                name="question_group_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0",
            name=op.f("ck_question_groups_content_not_blank"),
        ),
        sa.CheckConstraint(
            "difficulty BETWEEN 0.0 AND 1.0",
            name=op.f("ck_question_groups_difficulty_range"),
        ),
        sa.CheckConstraint(
            "length(trim(source_type)) > 0",
            name=op.f("ck_question_groups_source_type_not_blank"),
        ),
        sa.CheckConstraint(
            "source_reference IS NULL OR length(trim(source_reference)) > 0",
            name=op.f("ck_question_groups_source_reference_not_blank"),
        ),
        sa.CheckConstraint(
            "source_year IS NULL OR source_year BETWEEN 1900 AND 2100",
            name=op.f("ck_question_groups_source_year_range"),
        ),
        sa.CheckConstraint(
            "exam_weight BETWEEN 0.0 AND 1.0",
            name=op.f("ck_question_groups_exam_weight_range"),
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_question_groups_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_question_groups_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_groups")),
    )
    op.create_index(
        "ix_question_groups_subject_status",
        "question_groups",
        ["subject_id", "status"],
    )
    op.create_index(
        "ix_question_groups_created_by",
        "question_groups",
        ["created_by"],
    )

    op.create_table(
        "question_group_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(1), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "label IN ('a', 'b', 'c', 'd')",
            name=op.f("ck_question_group_items_label_allowed"),
        ),
        sa.CheckConstraint(
            "order_index BETWEEN 0 AND 3",
            name=op.f("ck_question_group_items_order_index_range"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["question_groups.id"],
            name=op.f("fk_question_group_items_group_id_question_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_group_items_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_group_items")),
        sa.UniqueConstraint(
            "group_id", "label", name="uq_question_group_items_group_label"
        ),
        sa.UniqueConstraint(
            "group_id", "order_index", name="uq_question_group_items_group_order"
        ),
        sa.UniqueConstraint(
            "question_id", name="uq_question_group_items_question"
        ),
    )


def downgrade() -> None:
    op.drop_table("question_group_items")
    op.drop_index("ix_question_groups_created_by", table_name="question_groups")
    op.drop_index("ix_question_groups_subject_status", table_name="question_groups")
    op.drop_table("question_groups")
