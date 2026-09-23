"""Add exam simulator tables.

Revision ID: 0026_exam_simulator
Revises: 0025_assignment_system
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0026_exam_simulator"
down_revision: str | Sequence[str] | None = "0025_assignment_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. exams
    op.create_table(
        "exams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), server_default="90", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PUBLISHED",
                "ARCHIVED",
                name="exam_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column(
            "exam_type",
            sa.Enum(
                "REAL_SIMULATION",
                "MOCK_PRACTICE",
                "DIAGNOSTIC_EXAM",
                name="exam_type",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="REAL_SIMULATION",
            nullable=False,
        ),
        sa.Column("total_questions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_points", sa.Float(), server_default="10.0", nullable=False),
        sa.Column("passing_score", sa.Float(), nullable=True),
        sa.Column("blueprint_config", sa.JSON(), nullable=True),
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
            "length(trim(title)) > 0",
            name=op.f("ck_exams_title_not_blank"),
        ),
        sa.CheckConstraint(
            "duration_minutes > 0",
            name=op.f("ck_exams_duration_positive"),
        ),
        sa.CheckConstraint(
            "total_points > 0",
            name=op.f("ck_exams_total_points_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_exams_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_exams_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exams")),
    )
    op.create_index(
        op.f("ix_exams_subject_status"),
        "exams",
        ["subject_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exams_created_by"),
        "exams",
        ["created_by"],
        unique=False,
    )

    # 2. exam_sections
    op.create_table(
        "exam_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("section_points", sa.Float(), nullable=True),
        sa.Column("blueprint_config", sa.JSON(), nullable=True),
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
            "length(trim(title)) > 0",
            name=op.f("ck_exam_sections_title_not_blank"),
        ),
        sa.CheckConstraint(
            "order_index >= 0",
            name=op.f("ck_exam_sections_order_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name=op.f("fk_exam_sections_exam_id_exams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_sections")),
    )
    op.create_index(
        op.f("ix_exam_sections_exam_order"),
        "exam_sections",
        ["exam_id", "order_index"],
        unique=False,
    )

    # 3. exam_questions
    op.create_table(
        "exam_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("points", sa.Float(), server_default="1.0", nullable=False),
        sa.CheckConstraint(
            "points > 0",
            name=op.f("ck_exam_questions_points_positive"),
        ),
        sa.CheckConstraint(
            "order_index >= 0",
            name=op.f("ck_exam_questions_order_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name=op.f("fk_exam_questions_exam_id_exams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["exam_sections.id"],
            name=op.f("fk_exam_questions_section_id_exam_sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_exam_questions_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_questions")),
        sa.UniqueConstraint(
            "exam_id",
            "question_id",
            name=op.f("uq_exam_questions_exam_question"),
        ),
        sa.UniqueConstraint(
            "exam_id",
            "order_index",
            name=op.f("uq_exam_questions_exam_order"),
        ),
    )
    op.create_index(
        op.f("ix_exam_questions_exam_id"),
        "exam_questions",
        ["exam_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exam_questions_section_id"),
        "exam_questions",
        ["section_id"],
        unique=False,
    )

    # 4. exam_attempts
    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "IN_PROGRESS",
                "SUBMITTED",
                "GRADED",
                "TIMED_OUT",
                "ABANDONED",
                name="exam_attempt_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="IN_PROGRESS",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("total_points", sa.Float(), server_default="10.0", nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
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
            "duration_seconds >= 0",
            name=op.f("ck_exam_attempts_duration_seconds_nonnegative"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR score >= 0",
            name=op.f("ck_exam_attempts_score_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name=op.f("fk_exam_attempts_exam_id_exams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_exam_attempts_student_id_student_profiles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_attempts")),
    )
    op.create_index(
        op.f("ix_exam_attempts_student_status"),
        "exam_attempts",
        ["student_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exam_attempts_exam_student"),
        "exam_attempts",
        ["exam_id", "student_id"],
        unique=False,
    )

    # 5. exam_responses
    op.create_table(
        "exam_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("student_answer", sa.Text(), nullable=True),
        sa.Column("selected_option_id", sa.Uuid(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score_awarded", sa.Float(), nullable=True),
        sa.Column("response_time_seconds", sa.Float(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_answered", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "score_awarded IS NULL OR score_awarded >= 0",
            name=op.f("ck_exam_responses_score_awarded_nonnegative"),
        ),
        sa.CheckConstraint(
            "response_time_seconds IS NULL OR response_time_seconds >= 0",
            name=op.f("ck_exam_responses_response_time_nonnegative"),
        ),
        sa.CheckConstraint(
            "order_answered >= 0",
            name=op.f("ck_exam_responses_order_answered_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["exam_attempts.id"],
            name=op.f("fk_exam_responses_attempt_id_exam_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_exam_responses_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_responses")),
        sa.UniqueConstraint(
            "attempt_id",
            "question_id",
            name=op.f("uq_exam_responses_attempt_question"),
        ),
    )
    op.create_index(
        op.f("ix_exam_responses_attempt_id"),
        "exam_responses",
        ["attempt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exam_responses_question_id"),
        "exam_responses",
        ["question_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("exam_responses")
    op.drop_table("exam_attempts")
    op.drop_table("exam_questions")
    op.drop_table("exam_sections")
    op.drop_table("exams")
