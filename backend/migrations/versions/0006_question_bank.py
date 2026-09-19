"""Question Bank with options, concept weights, and review workflow.

Revision ID: 0006_question_bank
Revises: 0005_classrooms
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_question_bank"
down_revision: str | Sequence[str] | None = "0005_classrooms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "question_type",
            sa.Enum(
                "MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER", "OPEN_RESPONSE",
                native_enum=False, create_constraint=True, name="question_type",
            ),
            nullable=False,
        ),
        sa.Column("difficulty", sa.Float(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("exam_weight", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "REVIEW", "APPROVED", "ARCHIVED",
                native_enum=False, create_constraint=True, name="question_status",
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(content)) > 0", name=op.f("ck_questions_content_not_blank")),
        sa.CheckConstraint("difficulty BETWEEN 0.0 AND 1.0", name=op.f("ck_questions_difficulty_range")),
        sa.CheckConstraint("length(trim(source_type)) > 0", name=op.f("ck_questions_source_type_not_blank")),
        sa.CheckConstraint("exam_weight BETWEEN 0.0 AND 1.0", name=op.f("ck_questions_exam_weight_range")),
        sa.CheckConstraint(
            "correct_answer IS NULL OR length(trim(correct_answer)) > 0",
            name=op.f("ck_questions_correct_answer_not_blank"),
        ),
        sa.CheckConstraint(
            "explanation IS NULL OR length(trim(explanation)) > 0",
            name=op.f("ck_questions_explanation_not_blank"),
        ),
        sa.CheckConstraint(
            "source_reference IS NULL OR length(trim(source_reference)) > 0",
            name=op.f("ck_questions_source_reference_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_questions_subject_id_subjects"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_questions_created_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_index(
        "ix_questions_subject_status_type_difficulty",
        "questions", ["subject_id", "status", "question_type", "difficulty"],
    )
    op.create_index("ix_questions_created_by", "questions", ["created_by"])

    op.create_table(
        "question_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(trim(label)) > 0", name=op.f("ck_question_options_label_not_blank")),
        sa.CheckConstraint("length(trim(content)) > 0", name=op.f("ck_question_options_content_not_blank")),
        sa.CheckConstraint("order_index >= 0", name=op.f("ck_question_options_order_index_nonnegative")),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"],
            name=op.f("fk_question_options_question_id_questions"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_options")),
        sa.UniqueConstraint("question_id", "label", name="uq_question_options_question_label"),
        sa.UniqueConstraint("question_id", "order_index", name="uq_question_options_question_order"),
    )

    op.create_table(
        "question_concepts",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.CheckConstraint("weight > 0.0 AND weight <= 1.0", name=op.f("ck_question_concepts_weight_range")),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"],
            name=op.f("fk_question_concepts_question_id_questions"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"], ["concepts.id"],
            name=op.f("fk_question_concepts_concept_id_concepts"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("question_id", "concept_id", name=op.f("pk_question_concepts")),
    )
    op.create_index(
        "ix_question_concepts_concept_question", "question_concepts", ["concept_id", "question_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_question_concepts_concept_question", table_name="question_concepts")
    op.drop_table("question_concepts")
    op.drop_table("question_options")
    op.drop_index("ix_questions_created_by", table_name="questions")
    op.drop_index("ix_questions_subject_status_type_difficulty", table_name="questions")
    op.drop_table("questions")
