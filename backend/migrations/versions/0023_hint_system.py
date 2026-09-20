"""Add predefined and issued progressive hints.

Revision ID: 0023_hint_system
Revises: 0022_question_attempt_evaluation_details
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0023_hint_system"
down_revision: str | Sequence[str] | None = "0022_question_attempt_evaluation_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hint_level() -> sa.Enum:
    return sa.Enum(
        "LEVEL_1",
        "LEVEL_2",
        "LEVEL_3",
        "LEVEL_4",
        name="hint_level",
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    op.create_table(
        "question_hints",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("hint_level", _hint_level(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(trim(content)) > 0",
            name=op.f("ck_question_hints_content_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_hints_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "question_id",
            "hint_level",
            name=op.f("pk_question_hints"),
        ),
    )

    op.create_table(
        "practice_question_hints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("practice_session_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("hint_level", _hint_level(), nullable=False),
        sa.Column("hint_count", sa.Integer(), nullable=False),
        sa.Column(
            "hint_source",
            sa.Enum(
                "PREDEFINED",
                "AI",
                name="hint_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "hint_count BETWEEN 1 AND 4",
            name=op.f("ck_practice_question_hints_hint_count_range"),
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0",
            name=op.f("ck_practice_question_hints_content_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["practice_session_id", "student_id"],
            ["practice_sessions.id", "practice_sessions.student_id"],
            name="fk_practice_question_hints_session_student",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_practice_question_hints_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_practice_question_hints")),
        sa.UniqueConstraint(
            "practice_session_id",
            "question_id",
            "hint_level",
            name="uq_practice_question_hints_session_question_level",
        ),
        sa.UniqueConstraint(
            "practice_session_id",
            "question_id",
            "hint_count",
            name="uq_practice_question_hints_session_question_count",
        ),
    )
    op.create_index(
        "ix_practice_question_hints_session_question",
        "practice_question_hints",
        ["practice_session_id", "question_id"],
        unique=False,
    )
    op.create_index(
        "ix_practice_question_hints_student_created",
        "practice_question_hints",
        ["student_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_practice_question_hints_student_created",
        table_name="practice_question_hints",
    )
    op.drop_index(
        "ix_practice_question_hints_session_question",
        table_name="practice_question_hints",
    )
    op.drop_table("practice_question_hints")
    op.drop_table("question_hints")
