"""Practice sessions, deterministic attempts, and classification scopes.

Revision ID: 0010_practice_engine
Revises: 0009_curriculum_refactor
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_practice_engine"
down_revision: str | Sequence[str] | None = "0009_curriculum_refactor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column(
            "session_type",
            sa.Enum(
                "DIAGNOSTIC",
                "PRACTICE",
                "REVIEW",
                "REPAIR",
                "QUICK_CHECK",
                "EXAM",
                native_enum=False,
                create_constraint=True,
                name="practice_session_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "COMPLETED",
                "ABANDONED",
                native_enum=False,
                create_constraint=True,
                name="practice_session_status",
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'ABANDONED') AND completed_at IS NOT NULL)",
            name=op.f("ck_practice_sessions_status_completed_at_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_practice_sessions_student_id_student_profiles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_practice_sessions_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_practice_sessions")),
        sa.UniqueConstraint(
            "id", "student_id", name=op.f("uq_practice_sessions_id_student_id")
        ),
    )
    op.create_index(
        "ix_practice_sessions_student_status_started",
        "practice_sessions",
        ["student_id", "status", "started_at"],
    )
    op.create_table(
        "practice_session_problem_types",
        sa.Column("practice_session_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["practice_session_id"],
            ["practice_sessions.id"],
            name=op.f(
                "fk_practice_session_problem_types_practice_session_id_practice_sessions"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            name=op.f(
                "fk_practice_session_problem_types_problem_type_id_problem_types"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "practice_session_id",
            "problem_type_id",
            name=op.f("pk_practice_session_problem_types"),
        ),
    )
    op.create_table(
        "practice_session_concepts",
        sa.Column("practice_session_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["practice_session_id"],
            ["practice_sessions.id"],
            name=op.f("fk_practice_session_concepts_practice_session_id_practice_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_practice_session_concepts_concept_id_concepts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "practice_session_id",
            "concept_id",
            name=op.f("pk_practice_session_concepts"),
        ),
    )
    op.create_table(
        "question_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("practice_session_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("student_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("response_time_seconds", sa.Float(), nullable=True),
        sa.Column("hint_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "evaluation_status",
            sa.Enum(
                "AUTO_EVALUATED",
                "NEEDS_EVALUATION",
                "EVALUATED",
                "NEEDS_TEACHER_REVIEW",
                native_enum=False,
                create_constraint=True,
                name="question_attempt_evaluation_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(student_answer)) > 0",
            name=op.f("ck_question_attempts_student_answer_not_blank"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0.0 AND 1.0",
            name=op.f("ck_question_attempts_score_range"),
        ),
        sa.CheckConstraint(
            "response_time_seconds IS NULL OR response_time_seconds > 0",
            name=op.f("ck_question_attempts_response_time_positive"),
        ),
        sa.CheckConstraint(
            "hint_count >= 0", name=op.f("ck_question_attempts_hint_count_nonnegative")
        ),
        sa.CheckConstraint(
            "attempt_number > 0", name=op.f("ck_question_attempts_attempt_number_positive")
        ),
        sa.ForeignKeyConstraint(
            ["practice_session_id", "student_id"],
            ["practice_sessions.id", "practice_sessions.student_id"],
            name="fk_question_attempts_session_student_practice_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_attempts_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_attempts")),
        sa.UniqueConstraint(
            "practice_session_id",
            "question_id",
            name=op.f("uq_question_attempts_session_question"),
        ),
        sa.UniqueConstraint(
            "practice_session_id",
            "attempt_number",
            name=op.f("uq_question_attempts_session_attempt_number"),
        ),
    )
    op.create_index(
        "ix_question_attempts_student_created",
        "question_attempts",
        ["student_id", "created_at"],
    )
    op.create_index(
        "ix_question_attempts_question_created",
        "question_attempts",
        ["question_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_question_attempts_question_created", table_name="question_attempts")
    op.drop_index("ix_question_attempts_student_created", table_name="question_attempts")
    op.drop_table("question_attempts")
    op.drop_table("practice_session_concepts")
    op.drop_table("practice_session_problem_types")
    op.drop_index(
        "ix_practice_sessions_student_status_started", table_name="practice_sessions"
    )
    op.drop_table("practice_sessions")

