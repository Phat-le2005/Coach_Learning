"""Add assignment system tables.

Revision ID: 0025_assignment_system
Revises: 0024_misconception_domain
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0025_assignment_system"
down_revision: str | Sequence[str] | None = "0024_misconception_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. assignments
    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "assignment_type",
            sa.Enum(
                "SAME_SET",
                "ADAPTIVE_SET",
                name="assignment_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PUBLISHED",
                "CLOSED",
                "ARCHIVED",
                name="assignment_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("question_count", sa.Integer(), server_default="5", nullable=False),
        sa.Column("difficulty_distribution", sa.JSON(), nullable=True),
        sa.Column(
            "start_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("ck_assignments_title_not_blank"),
        ),
        sa.CheckConstraint(
            "question_count > 0",
            name=op.f("ck_assignments_question_count_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_assignments_classroom_id_classrooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_assignments_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_assignments_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
    )
    op.create_index(
        "ix_assignments_classroom_status",
        "assignments",
        ["classroom_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_assignments_created_by",
        "assignments",
        ["created_by"],
        unique=False,
    )

    # 2. assignment_learning_objectives
    op.create_table(
        "assignment_learning_objectives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("learning_outcome_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_assignment_learning_objectives_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learning_outcome_id"],
            ["learning_outcomes.id"],
            name=op.f("fk_assignment_learning_objectives_learning_outcome_id_learning_outcomes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_learning_objectives")),
        sa.UniqueConstraint(
            "assignment_id",
            "learning_outcome_id",
            name=op.f("uq_assignment_learning_objectives_assignment_id_learning_outcome_id"),
        ),
    )
    op.create_index(
        "ix_assignment_learning_objectives_assignment_id",
        "assignment_learning_objectives",
        ["assignment_id"],
        unique=False,
    )

    # 3. assignment_problem_types
    op.create_table(
        "assignment_problem_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_assignment_problem_types_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            name=op.f("fk_assignment_problem_types_problem_type_id_problem_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_problem_types")),
        sa.UniqueConstraint(
            "assignment_id",
            "problem_type_id",
            name=op.f("uq_assignment_problem_types_assignment_id_problem_type_id"),
        ),
    )
    op.create_index(
        "ix_assignment_problem_types_assignment_id",
        "assignment_problem_types",
        ["assignment_id"],
        unique=False,
    )

    # 4. assignment_concepts
    op.create_table(
        "assignment_concepts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_assignment_concepts_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_assignment_concepts_concept_id_concepts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_concepts")),
        sa.UniqueConstraint(
            "assignment_id",
            "concept_id",
            name=op.f("uq_assignment_concepts_assignment_id_concept_id"),
        ),
    )
    op.create_index(
        "ix_assignment_concepts_assignment_id",
        "assignment_concepts",
        ["assignment_id"],
        unique=False,
    )

    # 5. assignment_questions
    op.create_table(
        "assignment_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_assignment_questions_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_assignment_questions_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_questions")),
        sa.UniqueConstraint(
            "assignment_id",
            "question_id",
            name=op.f("uq_assignment_questions_assignment_id_question_id"),
        ),
    )
    op.create_index(
        "ix_assignment_questions_assignment_id",
        "assignment_questions",
        ["assignment_id"],
        unique=False,
    )

    # 6. student_assignments
    op.create_table(
        "student_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "NOT_STARTED",
                "IN_PROGRESS",
                "SUBMITTED",
                "GRADED",
                name="student_assignment_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_student_assignments_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_student_assignments_student_id_student_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_assignments")),
        sa.UniqueConstraint(
            "assignment_id",
            "student_id",
            name=op.f("uq_student_assignments_assignment_id_student_id"),
        ),
    )
    op.create_index(
        "ix_student_assignments_assignment_status",
        "student_assignments",
        ["assignment_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_student_assignments_student_id",
        "student_assignments",
        ["student_id"],
        unique=False,
    )

    # 7. assignment_student_questions
    op.create_table(
        "assignment_student_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_assignment_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("student_answer", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["student_assignment_id"],
            ["student_assignments.id"],
            name=op.f("fk_assignment_student_questions_student_assignment_id_student_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_assignment_student_questions_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_student_questions")),
        sa.UniqueConstraint(
            "student_assignment_id",
            "question_id",
            name=op.f("uq_assignment_student_questions_student_assignment_id_question_id"),
        ),
    )
    op.create_index(
        "ix_assignment_student_questions_student_assignment_id",
        "assignment_student_questions",
        ["student_assignment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assignment_student_questions_student_assignment_id",
        table_name="assignment_student_questions",
    )
    op.drop_table("assignment_student_questions")

    op.drop_index(
        "ix_student_assignments_student_id",
        table_name="student_assignments",
    )
    op.drop_index(
        "ix_student_assignments_assignment_status",
        table_name="student_assignments",
    )
    op.drop_table("student_assignments")

    op.drop_index(
        "ix_assignment_questions_assignment_id",
        table_name="assignment_questions",
    )
    op.drop_table("assignment_questions")

    op.drop_index(
        "ix_assignment_concepts_assignment_id",
        table_name="assignment_concepts",
    )
    op.drop_table("assignment_concepts")

    op.drop_index(
        "ix_assignment_problem_types_assignment_id",
        table_name="assignment_problem_types",
    )
    op.drop_table("assignment_problem_types")

    op.drop_index(
        "ix_assignment_learning_objectives_assignment_id",
        table_name="assignment_learning_objectives",
    )
    op.drop_table("assignment_learning_objectives")

    op.drop_index(
        "ix_assignments_created_by",
        table_name="assignments",
    )
    op.drop_index(
        "ix_assignments_classroom_status",
        table_name="assignments",
    )
    op.drop_table("assignments")
