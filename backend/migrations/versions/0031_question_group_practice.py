"""Add group-aware practice attempts.

Revision ID: 0031_question_group_practice
Revises: 0030_question_groups
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0031_question_group_practice"
down_revision: str | Sequence[str] | None = "0030_question_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_group_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("practice_session_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("question_group_id", sa.Uuid(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("response_time_seconds", sa.Float(), nullable=True),
        sa.Column(
            "scoring_policy",
            sa.Enum(
                "MOET_2025_TRUE_FALSE",
                name="question_group_attempt_scoring_policy",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "correct_count BETWEEN 0 AND 4",
            name=op.f("ck_question_group_attempts_correct_count_range"),
        ),
        sa.CheckConstraint(
            "score BETWEEN 0.0 AND 1.0",
            name=op.f("ck_question_group_attempts_score_range"),
        ),
        sa.CheckConstraint(
            "response_time_seconds IS NULL OR response_time_seconds > 0",
            name=op.f("ck_question_group_attempts_response_time_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["practice_session_id", "student_id"],
            ["practice_sessions.id", "practice_sessions.student_id"],
            name="fk_group_attempts_session_student_practice_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_group_id"],
            ["question_groups.id"],
            name=op.f(
                "fk_question_group_attempts_question_group_id_question_groups"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_group_attempts")),
        sa.UniqueConstraint(
            "practice_session_id",
            "question_group_id",
            name="uq_question_group_attempts_session_group",
        ),
    )
    op.create_index(
        "ix_question_group_attempts_student_created",
        "question_group_attempts",
        ["student_id", "created_at"],
    )
    op.create_index(
        "ix_question_group_attempts_group_created",
        "question_group_attempts",
        ["question_group_id", "created_at"],
    )

    op.create_table(
        "question_group_attempt_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_group_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_group_item_id", sa.Uuid(), nullable=False),
        sa.Column("question_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(1), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "label IN ('a', 'b', 'c', 'd')",
            name=op.f("ck_question_group_attempt_items_label_allowed"),
        ),
        sa.CheckConstraint(
            "order_index BETWEEN 0 AND 3",
            name=op.f("ck_question_group_attempt_items_order_index_range"),
        ),
        sa.ForeignKeyConstraint(
            ["question_group_attempt_id"],
            ["question_group_attempts.id"],
            name=op.f(
                "fk_question_group_attempt_items_question_group_attempt_id_question_group_attempts"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_group_item_id"],
            ["question_group_items.id"],
            name=op.f(
                "fk_question_group_attempt_items_question_group_item_id_question_group_items"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_attempt_id"],
            ["question_attempts.id"],
            name=op.f(
                "fk_question_group_attempt_items_question_attempt_id_question_attempts"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_group_attempt_items")),
        sa.UniqueConstraint(
            "question_group_attempt_id",
            "label",
            name="uq_question_group_attempt_items_parent_label",
        ),
        sa.UniqueConstraint(
            "question_group_attempt_id",
            "order_index",
            name="uq_question_group_attempt_items_parent_order",
        ),
        sa.UniqueConstraint(
            "question_attempt_id",
            name="uq_question_group_attempt_items_question_attempt",
        ),
    )
    op.create_index(
        "ix_question_group_attempt_items_group_item",
        "question_group_attempt_items",
        ["question_group_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_question_group_attempt_items_group_item",
        table_name="question_group_attempt_items",
    )
    op.drop_table("question_group_attempt_items")
    op.drop_index(
        "ix_question_group_attempts_group_created",
        table_name="question_group_attempts",
    )
    op.drop_index(
        "ix_question_group_attempts_student_created",
        table_name="question_group_attempts",
    )
    op.drop_table("question_group_attempts")
