"""Add tutor sessions, tutor session summaries, and student learning memories.

Revision ID: 0029_tutor_learning_memory
Revises: 0028_admission_import
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0029_tutor_learning_memory"
down_revision: str | Sequence[str] | None = "0028_admission_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. tutor_sessions
    op.create_table(
        "tutor_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("problem_type_id", sa.Uuid(), nullable=True),
        sa.Column("concept_id", sa.Uuid(), nullable=True),
        sa.Column("question_id", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "turn_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "COMPLETED",
                "ABANDONED",
                name="tutor_session_status",
                native_enum=False,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "turn_count >= 0",
            name="tutor_sessions_turn_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tutor_sessions_student_id", "tutor_sessions", ["student_id"])
    op.create_index("ix_tutor_sessions_student_status", "tutor_sessions", ["student_id", "status"])
    op.create_index("ix_tutor_sessions_student_started", "tutor_sessions", ["student_id", "started_at"])

    # 2. tutor_session_summaries
    op.create_table(
        "tutor_session_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("key_takeaways", sa.JSON(), nullable=False),
        sa.Column(
            "resolved_questions_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["tutor_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tutor_session_summaries_student_id", "tutor_session_summaries", ["student_id"])
    op.create_index("ix_tutor_session_summaries_session_id", "tutor_session_summaries", ["session_id"], unique=True)

    # 3. student_learning_memories
    op.create_table(
        "student_learning_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "LEARNING_PREFERENCE",
                "PERSISTENT_DIFFICULTY",
                "PERSISTENT_MISCONCEPTION",
                "IMPORTANT_ACADEMIC_GOAL",
                "TUTORING_PREFERENCE",
                name="learning_memory_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("problem_type_id", sa.Uuid(), nullable=True),
        sa.Column("concept_id", sa.Uuid(), nullable=True),
        sa.Column("source_session_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name="learning_memory_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["tutor_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_student_learning_memories_student_id", "student_learning_memories", ["student_id"])
    op.create_index(
        "ix_student_learning_memories_student_type",
        "student_learning_memories",
        ["student_id", "type"],
    )
    op.create_index(
        "ix_student_learning_memories_student_concept",
        "student_learning_memories",
        ["student_id", "concept_id"],
    )
    op.create_index(
        "ix_student_learning_memories_student_pt",
        "student_learning_memories",
        ["student_id", "problem_type_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_learning_memories_student_pt", table_name="student_learning_memories")
    op.drop_index("ix_student_learning_memories_student_concept", table_name="student_learning_memories")
    op.drop_index("ix_student_learning_memories_student_type", table_name="student_learning_memories")
    op.drop_index("ix_student_learning_memories_student_id", table_name="student_learning_memories")
    op.drop_table("student_learning_memories")

    op.drop_index("ix_tutor_session_summaries_session_id", table_name="tutor_session_summaries")
    op.drop_index("ix_tutor_session_summaries_student_id", table_name="tutor_session_summaries")
    op.drop_table("tutor_session_summaries")

    op.drop_index("ix_tutor_sessions_student_started", table_name="tutor_sessions")
    op.drop_index("ix_tutor_sessions_student_status", table_name="tutor_sessions")
    op.drop_index("ix_tutor_sessions_student_id", table_name="tutor_sessions")
    op.drop_table("tutor_sessions")
